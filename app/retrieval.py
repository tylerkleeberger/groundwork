"""P1-T7 hybrid retrieval pure logic: reciprocal rank fusion (offline-tested,
D16 unmarked). The SQL and embedding calls live in app/main.py; this module
owns only the merge math so the offline CI floor can verify it.

RRF: score(d) = Σ_r weight_r / (k + rank_r(d)), rank 1-based, over each
ranking r that contains d. Documents absent from a ranking simply contribute
nothing from it — no penalty term.
"""
from __future__ import annotations

import json
import pathlib
from typing import Hashable

CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent / "config" / "retrieval.json"


def load_retrieval_config() -> dict:
    """Retrieval knobs for the ACTIVE corpus profile (P5-T3).

    THRESHOLDS BELONG TO THEIR INPUT DISTRIBUTION — the standing rule since
    T8, restated by the P5-T3 ruling. The not-found gate's -1.67 was derived
    against the personal corpus's rerank-score distribution; a different
    corpus is a different distribution, and carrying the number across would
    be reusing a measurement as if it were a constant.

    A profile that names no `retrieval_config` gets `config/retrieval.json`,
    i.e. exactly the file this function has always read — the personal path
    is unchanged by construction, not by argument.
    """
    from app.profile import load_profile  # local: retrieval.py stays import-light

    override = load_profile().retrieval_config
    return json.loads((override or CONFIG_PATH).read_text())


def rrf_merge(
    rankings: dict[str, list[Hashable]],
    k: int = 60,
    weights: dict[str, float] | None = None,
) -> list[Hashable]:
    """Merge named rankings (each an ordered list of ids, best first) into
    one fused ordering. Ties break deterministically by first appearance
    order across rankings (stable for reproducible evals)."""
    weights = weights or {}
    scores: dict[Hashable, float] = {}
    first_seen: dict[Hashable, int] = {}
    counter = 0
    for name, ranking in rankings.items():
        w = weights.get(name, 1.0)
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + w / (k + rank)
            if doc not in first_seen:
                first_seen[doc] = counter
                counter += 1
    return sorted(scores, key=lambda d: (-scores[d], first_seen[d]))


def should_decline(gate_score: float | None, cfg: dict) -> bool:
    """T8 not-found gate: decline when the best rerank score is below the
    calibrated threshold. No signal (reranker off / no candidates) => never
    auto-decline — the gate only acts on evidence."""
    nf = cfg.get("not_found", {})
    if not nf.get("enabled") or gate_score is None:
        return False
    return gate_score < nf["min_rerank_score"]


def aggregate_sources(rows: list[dict], scores: list[float],
                      top_k: int = 10) -> list[dict]:
    """P2-T1 /related: roll per-chunk candidates up to SOURCE level — the
    KB-review question is "what documents exist", not "which chunks".
    rows: chunk dicts (source_id/title/source_table/similarity), scores:
    the parallel cross-encoder scores. Sorted by best rerank score."""
    by_source: dict[str, dict] = {}
    for row, score in zip(rows, scores, strict=True):
        s = by_source.setdefault(row["source_id"], {
            "source_id": row["source_id"], "title": row.get("title"),
            "source_table": row.get("source_table"),
            "best_similarity": row["similarity"],
            "best_rerank_score": score, "chunk_hits": 0,
        })
        s["chunk_hits"] += 1
        s["best_similarity"] = max(s["best_similarity"], row["similarity"])
        s["best_rerank_score"] = max(s["best_rerank_score"], score)
    ranked = sorted(by_source.values(),
                    key=lambda s: -s["best_rerank_score"])[:top_k]
    for s in ranked:
        s["best_similarity"] = round(s["best_similarity"], 4)
        s["best_rerank_score"] = round(s["best_rerank_score"], 4)
    return ranked


def related_verdict(gate_score: float | None, cfg: dict) -> str:
    """Coverage verdict for /related, from config bands (NOT the ask-gate
    threshold: T8 lesson applied forward — thresholds are calibrated to
    their input distribution, and bare topics score differently than
    questions; see the P2-T1 spot-check in the journal)."""
    bands = cfg.get("related_bands", {})
    if gate_score is None:
        return "unknown"
    if gate_score >= bands.get("covered_min", 0.0):
        return "likely covered"
    if gate_score >= bands.get("adjacent_min", -4.0):
        return "adjacent material"
    return "nothing close"


def route_decision(gate_score: float | None, question: str,
                   cfg: dict) -> tuple[str, str]:
    """P2-T3 routing v1: choose the generator. First-pass conditional —
    the decision uses only pre-generation signals (gate_score exists at
    retrieval time), so marginal cases pay ONE generation, not two.
    Returns (model_alias, reason)."""
    r = cfg.get("routing", {})
    default = r.get("default_model", "cheap")
    if not r.get("enabled"):
        return default, "default"
    if question in set(r.get("always_frontier_questions", [])):
        return r.get("model", "frontier"), "flagged"
    band = r.get("escalate_band")
    if (gate_score is not None and band
            and band[0] <= gate_score < band[1]):
        return r.get("model", "frontier"), "marginal-band"
    return default, "default"
