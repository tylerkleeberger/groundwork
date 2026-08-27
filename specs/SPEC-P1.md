# SPEC-P1 — Ask: naive → measured → good

**Phase goal (from blueprint):** a working RAG pipeline over your chosen
corpus, with the golden set and eval harness making every improvement
measurable. Acceptance: faithfulness >0.9 and relevancy >0.85 on 30+ real
cases; documented before/after retrieval delta; "not found" fires correctly.

**Mode legend:** `[interactive]` = do in a live Claude Code session (novel /
architectural; your judgment needed in the loop). `[headless]` = eligible
for `./scripts/dispatch.sh <task-id>` once its dependencies are merged —
the spec below is its full definition of done. Tasks marked `[human]` are
yours alone.

---

### P1-T1 `[human]` Choose and stage the corpus
Pick the daily-useful corpus (your research docs, notes, project material)
AND note a public corpus for the demo config (an OSS project's docs).
Place personal corpus under `corpus/` (gitignored). ~50+ documents minimum
for retrieval to be interesting.

### P1-T2 `[interactive]` Ingestion v1
`ingest.py`: parse corpus files (md/txt/pdf) → chunk 400–800 tokens on
structural boundaries (headings > paragraphs; never mid-sentence) → attach
metadata {source_id, title, section, mtime} → embed → store in pgvector
table `chunks`. Embedding model configurable and version-pinned in config.
Idempotent: re-running updates changed docs (hash check), deletes removed.
Done: `python ingest.py corpus/` populates DB; re-run is a no-op on
unchanged corpus; a changed file re-indexes only itself.

### P1-T3 `[interactive]` Ask pipeline v1 (naive, end-to-end)
FastAPI `POST /ask {question}` → top-5 cosine from pgvector → generation
via gateway alias `cheap` with a grounding prompt that REQUIRES citations
in the form [source_id] and instructs "answer only from provided context;
otherwise say you don't know" → response
`{answer, citations[], confidence}` (confidence v1 = max retrieval score).
Every stage traced to Langfuse as child spans of one trace.
Done: curl returns a cited answer; trace tree shows retrieve→generate.

### P1-T4 `[human, ~2 focused hours]` Golden set to 30+
Replace placeholder cases in `evals/golden_set.jsonl` with real questions
against YOUR corpus: ≥22 answerable (with must_cite_sources filled from
sources you verify by hand), ≥5 not-in-corpus (confabulation guards),
≥3 with answer_must_not_contain traps from failures you observe in T3.
This is deliberately not delegable: the golden set is your proprietary
ground truth and the credibility of every number that follows.

### P1-T5 `[headless]` Wire the harness (deps: T3, T4)
Replace the `ask()` stub in `evals/test_evals.py` with a real call to
`POST /ask`. Add per-case retrieval scoring: context_precision (retrieved
chunks that are relevant / retrieved) and context_recall (required sources
found / required), written to `evals/results/<timestamp>.json` so deltas
are diffable across runs.
Settled semantics (T4 rulings, 2026-07-07): `answer_must_contain` matches
CASE-INSENSITIVELY (R1); `may_cite_any` accepts ANY ONE of the listed
source_ids (vs `must_cite_sources` = all required); one results file per
run into `evals/results/` (gitignored). The certified set is 29 cases
(24 answerable + 5 guards); `answer_must_not_contain` traps accrue later
per the standing first-three-observed-failures rule (R2) — the harness
must support the field even while no case uses it.
DISPATCH CONSTRAINT (D10 headless): worktrees contain no `.env`, so the
worker CANNOT run live cases. Worker definition of done = harness code +
offline tests green (`pytest -m "not live"`). Live golden-set-marked tests
must skip cleanly (not error) when the stack/env is absent. The FULL live
run (all 29 cases against the running stack) happens post-dispatch in the
main checkout, and its results file is the T7 baseline.
Done (worker): harness wired + offline green. Done (task): the live run
executes all 29 cases and emits the results file.

### P1-T6 `[headless]` Layer-2 judge (deps: T5)
Add LLM-as-judge scoring via gateway alias `cheap`: faithfulness (is every
claim in the answer supported by the retrieved chunks?) and relevancy
(does the answer address the question?), 0–1, rubric prompts stored in
`evals/judges/`. Runs on the golden set as part of pytest (marker
`@pytest.mark.judge`, skippable). Include 5 hand-labeled calibration cases
in the results output so judge drift is visible. Done: results file gains
faithfulness/relevancy columns; calibration agreement reported.

### P1-T7 `[interactive]` Retrieval v2 — hybrid + rerank (deps: T5)
BASELINE FIRST: run and save the eval results on v1. Then: add Postgres
FTS (tsvector) alongside vectors; query both in parallel; merge with
reciprocal rank fusion; widen to top-50; rerank to top-5 (Voyage/Cohere
rerank API, or local cross-encoder — decide by latency on your hardware).
Re-run evals. Done: before/after table in `evals/results/`, and the delta
written into BUILD_JOURNAL.md — this number is a resume line.

### P1-T8 `[headless]` Confidence + not-found behavior (deps: T7)
Calibrate a confidence threshold against the golden set's not-found cases:
below threshold → honest decline response, no fabricated citations. Add
`answer_must_not_contain` enforcement to guard traps. Done: all
`ask_notfound` cases pass; zero confabulated citations across the set.

### P1-T9 `[headless]` Ingestion sync worker (deps: T2)
One-command source-of-truth sync, safe on a schedule: `scripts/sync.py`
runs export → prune → ingest end-to-end:
- export (scripts/export_corpus.py logic) re-exports from
  APP_CORPUS_SOURCE_URL;
- PRUNE: corpus/*.md files whose rows no longer exist in the export set
  are removed — export overwrites in place and never deletes (learned at
  the 2026-07-12 Neon cleanup: stale files linger without this);
- ingest (ingest.py logic) re-embeds only deltas via the hash ledger and
  cascades deletions.
Requirements (T9 ruling, 2026-07-13): idempotent — a second run with no
source changes is a no-op; every run prints a per-stage summary AND logs a
sync summary trace to Langfuse; ANY stage failure → nonzero exit with an
unmissable message (never a silent partial sync); REFUSES to run — before
touching anything — if ingest_meta's embedding_model/dimensions mismatch
the code's pin (surface D17's refuse-to-mix loudly).
DISPATCH CONSTRAINT (D10): worktrees contain no `.env` and no live
services — the worker's definition of done is sync-worker code + offline
tests green (`pytest -m "not live"`); pure logic (prune-set computation,
summary assembly, pin-check decision) must be offline-tested. The live
end-to-end run happens post-dispatch in the main checkout.
Done (worker): code + offline green + REPORT.md (scope deviations
HEADLINED). Done (task): a live NO-CHANGE sync proves idempotency
end-to-end; touch one corpus file → only it re-indexes; delete → chunks
gone; the run is visible as a Langfuse trace.

---

**Phase gate:** all acceptance numbers met → paste the final eval results
and BUILD_JOURNAL excerpts to the director session → receive SPEC-P2
(routing, caching, local-model ownership decisions).

**Dispatch guidance:** T5 is the first safe headless candidate — verifiable,
bounded, low blast radius. Run it solo before ever dispatching in parallel;
graduate to parallel dispatch (e.g. T6+T9 together) only after one clean
solo review cycle. That graduation moment goes in the journal too.
