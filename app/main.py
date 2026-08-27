"""P1-T3 Ask pipeline v1 (naive, end-to-end) — SPEC-P1 T3.

POST /ask {question} -> {answer, citations[], confidence}.
Retrieval (P1-T7 v2): hybrid — dense cosine (pgvector) + BM25 (Postgres
FTS, tsvector) queried in parallel over top-50 each, merged with reciprocal
rank fusion, top-5 returned (reranker slot behind config, pending owner
ratification). Query embedded via gateway alias `embed` with
ingest.QUERY_PREFIX (the query-side prefix contract). Knobs live in
config/retrieval.json, not code.
Generation: gateway alias `cheap`, grounding prompt requiring [source_id]
citations, honest not-found otherwise.
Tracing: one Langfuse trace per request; retrieve is a child span, and the
gateway calls carry metadata.trace_id so their generations join the same
tree.

Run (from repo root): set -a; source .env; set +a
  .venv/bin/uvicorn app.main:app --port 8310
"""

import os

import psycopg

from fastapi import BackgroundTasks, FastAPI
from langfuse import Langfuse
from openai import OpenAI
from pydantic import BaseModel

from app.grounding import (NOT_FOUND_ANSWER, build_messages, confidence_from,
                           extract_citations)
from app.profile import load_profile
from app.reranker import rerank_scores, top_k_by_score
from app.retrieval import (aggregate_sources, load_retrieval_config,
                           related_verdict, route_decision, rrf_merge,
                           should_decline)
from ingest import EMBED_ALIAS, QUERY_PREFIX  # uvicorn runs from repo root


# D7 profile, read once at import the way config/retrieval.json is. Every
# connect site below passes its kwargs; for the personal profile they are
# EMPTY, so the pre-seam connection is reproduced argument-for-argument.
_PROFILE = load_profile()

app = FastAPI(title="Groundwork")
gateway = OpenAI(base_url=os.environ.get("GATEWAY", "http://localhost:4000"),
                 api_key="anything")
langfuse = Langfuse()  # reads LANGFUSE_* from env


class AskRequest(BaseModel):
    question: str


class RelatedRequest(BaseModel):
    topic: str
    top_k: int = 10


class RelatedSource(BaseModel):
    source_id: str
    title: str | None = None
    source_table: str | None = None
    best_similarity: float
    best_rerank_score: float
    chunk_hits: int


class RelatedResponse(BaseModel):
    topic: str
    verdict: str          # likely covered | adjacent material | nothing close
    gate_score: float | None
    sources: list[RelatedSource]


class RetrievedChunk(BaseModel):
    source_id: str
    title: str | None = None
    section: str | None = None
    source_table: str | None = None  # T8: record type (gs-024 — the generator
                                     # must SEE that a chunk is a session record)
    similarity: float
    content: str


class AskResponse(BaseModel):
    answer: str
    citations: list[str]
    confidence: float
    # P1-T5: the ranked per-chunk source_ids that retrieval returned (may
    # repeat a source across chunks). Additive, non-behavioral — the eval
    # harness needs the RETRIEVED set to score context_precision/recall, which
    # citations (a generator-chosen subset) cannot express. Also a useful
    # retrieval-debugging signal ahead of the T7 hybrid/rerank work.
    retrieved: list[str]
    # P2-T3: which generator produced this answer, and why. confidence and
    # gate_score keep their retrieval-derived, generator-independent
    # semantics — routing changes the GENERATOR only.
    routed_to: str = "cheap"
    route_reason: str = "default"
    # T8: the not-found gate signal — max cross-encoder score over the final
    # candidates. DISTINCT from `confidence` (max cosine): confidence describes
    # retrieval closeness, gate_score describes answerability. Surfaced so the
    # eval margin (worst answerable vs best guard) prints in every results file.
    gate_score: float | None = None
    # P1-T6: the retrieved chunks themselves. Additive, non-behavioral (same
    # ratification class as `retrieved`) — the faithfulness judge must check
    # every claim against the EXACT chunks the generator saw; ids alone can't
    # support that, and re-retrieving outside the request could drift.
    chunks: list[RetrievedChunk]
    # P3-T4: this answer's Langfuse trace id. Additive, non-behavioral (the
    # `retrieved`/`chunks` ratification class) — research workers call
    # run_ask() in-process and must record WHICH ask trace carries each
    # worker's cost, or per-role cost attribution (§D) has no join key.
    trace_id: str | None = None


def _hybrid_candidates(text: str, trace_id: str | None,
                       generation_name: str) -> tuple[list[dict], list[float], float | None, dict]:
    """Shared candidate pipeline for /ask and /related (P2-T1): embed →
    dense+BM25 → RRF → rerank scores over the candidate pool. Returns
    (candidate chunk dicts in fused order, parallel CE scores, gate_score,
    cfg). One implementation — /related must never drift from /ask."""
    cfg = load_retrieval_config()
    meta = {"generation_name": generation_name}
    if trace_id:
        meta["existing_trace_id"] = trace_id
    vec = gateway.embeddings.create(
        model=EMBED_ALIAS, input=[QUERY_PREFIX + text],
        extra_body={"metadata": meta},
    ).data[0].embedding
    with psycopg.connect(os.environ["APP_DATABASE_URL"],
                         **_PROFILE.connect_kwargs()) as conn:
        dense_ids = [r[0] for r in conn.execute(
            "SELECT id FROM chunks ORDER BY embedding <=> %s::vector LIMIT %s",
            (str(vec), cfg["dense_top_k"]),
        ).fetchall()]
        bm25_ids = [r[0] for r in conn.execute(
            """SELECT id FROM chunks
               WHERE tsv @@ plainto_tsquery('english', %s)
               ORDER BY ts_rank_cd(tsv, plainto_tsquery('english', %s)) DESC
               LIMIT %s""",
            (text, text, cfg["bm25_top_k"]),
        ).fetchall()]
        fused = rrf_merge({"dense": dense_ids, "bm25": bm25_ids},
                          k=cfg["rrf_k"], weights=cfg["rrf_weights"])
        rr = cfg["reranker"]
        take = rr["candidates"] if rr["enabled"] else cfg["final_top_k"]
        candidates = fused[:take]
        if not candidates:
            return [], [], None, cfg
        rows = conn.execute(
            """SELECT id, source_id, title, section, source_table, content,
                      1 - (embedding <=> %s::vector) AS similarity
               FROM chunks WHERE id = ANY(%s)""",
            (str(vec), candidates),
        ).fetchall()
    order = {cid: i for i, cid in enumerate(candidates)}
    rows.sort(key=lambda r: order[r[0]])
    dicts = [
        {"source_id": r[1], "title": r[2], "section": r[3],
         "source_table": r[4], "content": r[5], "similarity": float(r[6])}
        for r in rows
    ]
    scores: list[float] = []
    gate_score = None
    if rr["enabled"]:
        scores = rerank_scores(rr, text, [d["content"] for d in dicts])
        gate_score = round(max(scores), 4) if scores else None
    return dicts, scores, gate_score, cfg


def retrieve(question: str, trace_id: str) -> tuple[list[dict], float | None]:
    """Hybrid retrieval for /ask: candidates via the shared pipeline, then
    blend-reranked to final_top_k. Similarity is cosine (v1 scale)."""
    dicts, scores, gate_score, cfg = _hybrid_candidates(
        question, trace_id, "ask-embed-query")
    if not dicts:
        return [], None
    rr = cfg["reranker"]
    if rr["enabled"]:
        ce_order = top_k_by_score(list(range(len(dicts))), scores, len(dicts))
        if rr.get("blend_with_fused"):
            # CE reorders but cannot catastrophically demote: fuse the CE
            # ranking with the RRF prior (recall-floor incident, gs-014 —
            # the CE alone pushed a required rank-4 source to rank 6)
            blended = rrf_merge({"fused": list(range(len(dicts))),
                                 "ce": ce_order}, k=cfg["rrf_k"])
            ranked = blended[: cfg["final_top_k"]]
        else:
            ranked = ce_order[: cfg["final_top_k"]]
        dicts = [dicts[i] for i in ranked]
    else:
        dicts = dicts[: cfg["final_top_k"]]
    return dicts, gate_score


def run_ask(question: str) -> AskResponse:
    """P3-T3: the Ask pipeline as a callable seam (SPEC-P3 §A). Used by
    POST /ask below and, from T4, by research workers in-process — same
    code object, no HTTP self-call. Additive extraction of the T9
    run_export()/run_ingest() class: the body is the former ask() handler
    verbatim; behavior unchanged (exam evidence in the T3 PR)."""
    trace = langfuse.trace(name="ask", input={"question": question})

    span = trace.span(name="retrieve", input={"question": question,
                                              "mode": "hybrid-rrf"})
    chunks, gate_score = retrieve(question, trace.id)
    span.end(output=[{"source_id": c["source_id"], "title": c["title"],
                      "similarity": c["similarity"]} for c in chunks]
                    + [{"gate_score": gate_score}])

    # T8 not-found gate (owner-ratified): when the best rerank score says no
    # candidate can support an answer, decline honestly — and skip the
    # generation call entirely (a decline costs zero tokens).
    if should_decline(gate_score, load_retrieval_config()):
        resp = AskResponse(
            answer=NOT_FOUND_ANSWER, citations=[],
            confidence=confidence_from([c["similarity"] for c in chunks]),
            retrieved=[c["source_id"] for c in chunks],
            routed_to="none", route_reason="declined",  # no generation ran
            gate_score=gate_score,
            chunks=[RetrievedChunk(**c) for c in chunks],
            trace_id=trace.id,
        )
        trace.update(output=resp.model_dump(exclude={"chunks"}))
        langfuse.flush()
        return resp

    model, reason = route_decision(gate_score, question,
                                   load_retrieval_config())
    completion = gateway.chat.completions.create(
        model=model,
        max_tokens=1024,
        # temperature=0 is PRODUCT behavior, not an eval flag (gate ruling,
        # 2026-07-08): a grounded factual assistant is the product where
        # determinism is correct, and an eval-only pin would create eval/prod
        # skew — the exam measuring a system users don't get.
        temperature=0,
        messages=build_messages(question, chunks),
        # existing_trace_id (not trace_id): the app owns this trace; litellm's
        # callback must attach, not overwrite trace name/output (learned live)
        extra_body={"metadata": {"existing_trace_id": trace.id,
                                 "generation_name": "ask-generate"}},
    )
    answer = completion.choices[0].message.content or ""

    resp = AskResponse(
        answer=answer,
        citations=extract_citations(answer, [c["source_id"] for c in chunks]),
        confidence=confidence_from([c["similarity"] for c in chunks]),
        retrieved=[c["source_id"] for c in chunks],
        routed_to=model, route_reason=reason,
        gate_score=gate_score,
        chunks=[RetrievedChunk(**c) for c in chunks],
        trace_id=trace.id,
    )
    # chunks excluded from the trace payload: the retrieve span already logs
    # ids + similarities, and 5 full chunk texts per trace is pure bloat
    trace.update(output=resp.model_dump(exclude={"chunks"}))
    langfuse.flush()
    return resp


@app.post("/ask")
def ask(req: AskRequest) -> AskResponse:
    return run_ask(req.question)


def run_related(topic: str, top_k: int = 10) -> RelatedResponse:
    """P4-T2: the /related pipeline as a callable seam (the run_ask
    class of additive extraction, headlined): used by POST /related
    below and by the related_check MCP tool. Body moved verbatim;
    behavior unchanged (before/after response diff in the T2 PR)."""
    trace = langfuse.trace(name="related", input={"topic": topic})
    dicts, scores, gate_score, cfg = _hybrid_candidates(
        topic, trace.id, "related-embed-topic")
    sources = aggregate_sources(dicts, scores, top_k=top_k) if scores else []
    resp = RelatedResponse(
        topic=topic,
        verdict=related_verdict(gate_score, cfg),
        gate_score=gate_score,
        sources=[RelatedSource(**s) for s in sources],
    )
    trace.update(output=resp.model_dump())
    langfuse.flush()
    return resp


@app.post("/related")
def related(req: RelatedRequest) -> RelatedResponse:
    """P2-T1: pre-generation retrieval check — the external-KB seam.
    Retrieval WITHOUT generation (no LLM call, ~1s): "what already exists
    on this topic?" before a new KB entry is written. Contract documented
    in README § Integration contract."""
    return run_related(req.topic, req.top_k)


class ResearchRequest(BaseModel):
    question: str


@app.post("/research")
def research(req: ResearchRequest, background: BackgroundTasks) -> dict:
    """P3-T4: commission a research brief — returns immediately with the
    run id; execution proceeds in the background over checkpoints (a
    process death mid-run is resumable, §B)."""
    from app.research import _drive
    with psycopg.connect(os.environ["APP_DATABASE_URL"],
                         **_PROFILE.connect_kwargs(),
                         autocommit=True) as conn:
        from app.research_state import PostgresStore
        store = PostgresStore(conn)
        store.ensure_schema()
        run_id = store.create_run(req.question)
    background.add_task(_drive, run_id)
    return {"run_id": run_id, "status": "running"}


@app.get("/research/{run_id}")
def research_status(run_id: str) -> dict:
    """Run record (the T1 contract) + the $0 critic report once a brief
    exists. Chunks are stripped from the response — they are judge
    payload, not reader payload."""
    from app.research import critic_report
    with psycopg.connect(os.environ["APP_DATABASE_URL"],
                         **_PROFILE.connect_kwargs(),
                         autocommit=True) as conn:
        from app.research_state import PostgresStore
        run = PostgresStore(conn).load_run(run_id)
    for step in run["steps"]:
        if step.get("result"):
            step["result"].pop("chunks", None)
    if run.get("brief"):
        run["critic"] = critic_report(run)
    return run


@app.post("/research/{run_id}/resume")
def research_resume(run_id: str, background: BackgroundTasks) -> dict:
    """The §B resume verb: explicit, never automatic. Steps already done
    are never re-bought; the advisory lock refuses a double-resume."""
    from app.research import resume_research
    background.add_task(resume_research, run_id)
    return {"run_id": run_id, "status": "resuming"}
