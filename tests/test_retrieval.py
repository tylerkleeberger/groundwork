"""Offline tests for app/retrieval.py — RRF math and merge logic (D16
unmarked). The SQL/HTTP sides are covered by the live suite."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.retrieval import load_retrieval_config, rrf_merge  # noqa: E402

RETRIEVAL_JSON = Path(__file__).resolve().parent.parent / "config" / "retrieval.json"


def test_rrf_score_math_exact():
    # doc "a": rank 1 both lists → 2/(60+1); doc "b": rank 2 dense only → 1/62
    fused = rrf_merge({"dense": ["a", "b"], "bm25": ["a"]}, k=60)
    assert fused == ["a", "b"]


def test_rrf_both_lists_beats_same_rank_in_one():
    # "b" appears in both lists (1/62 + 1/61) and must beat "a", rank-1 in
    # dense only (1/61)
    fused = rrf_merge({"dense": ["a", "b"], "bm25": ["b", "x"]}, k=60)
    assert fused[0] == "b"


def test_rrf_convexity_extremes_edge_out_double_middle():
    # Documented property, verified numerically: rank-1+rank-3 (1/61 + 1/63)
    # slightly beats rank-2+rank-2 (2/62) — RRF's 1/(k+r) is convex. Encoded
    # so nobody "fixes" it into a bug later.
    fused = rrf_merge({"dense": ["a", "b", "c"], "bm25": ["c", "b", "a"]}, k=60)
    assert fused.index("b") == 2


def test_rrf_weights_shift_the_fusion():
    heavy_dense = rrf_merge({"dense": ["a"], "bm25": ["b"]}, k=60,
                            weights={"dense": 2.0, "bm25": 1.0})
    heavy_bm25 = rrf_merge({"dense": ["a"], "bm25": ["b"]}, k=60,
                           weights={"dense": 1.0, "bm25": 2.0})
    assert heavy_dense[0] == "a" and heavy_bm25[0] == "b"


def test_rrf_absent_doc_gets_no_penalty_and_ties_break_stably():
    # "a" and "b" have identical scores (same rank, same weight, different
    # lists) → tie breaks by first appearance: "a" (dense iterates first)
    fused = rrf_merge({"dense": ["a"], "bm25": ["b"]}, k=60)
    assert fused == ["a", "b"]


def test_rrf_handles_empty_rankings():
    assert rrf_merge({"dense": [], "bm25": []}, k=60) == []
    assert rrf_merge({"dense": ["a"], "bm25": []}, k=60) == ["a"]


def test_config_carries_the_knobs_not_code():
    cfg = load_retrieval_config()
    for key in ("dense_top_k", "bm25_top_k", "rrf_k", "rrf_weights",
                "final_top_k", "reranker"):
        assert key in cfg
    # reranker enablement + pinning asserted in tests/test_reranker.py
    # (ratified 2026-07-09)


def test_should_decline_gate_semantics():
    from app.retrieval import should_decline
    cfg = {"not_found": {"enabled": True, "min_rerank_score": -1.67}}
    assert should_decline(-2.07, cfg) is True    # best-guard territory
    assert should_decline(-1.27, cfg) is False   # worst-answerable territory
    assert should_decline(-1.67, cfg) is False   # boundary: not below
    assert should_decline(None, cfg) is False    # no signal -> never auto-decline
    assert should_decline(-9.0, {"not_found": {"enabled": False,
                                               "min_rerank_score": -1.67}}) is False


def test_not_found_config_present_and_calibrated():
    """The PERSONAL corpus's shipped calibration, asserted per-profile rather
    than via whatever profile happens to be active (P5-T3). The floor must not
    depend on a locally-switched config file — a test that turns red because
    someone is mid-demo-run is a test that teaches people to ignore it."""
    import json

    from app.profile import load_profile

    personal = load_profile("personal")
    assert personal.retrieval_config is None, (
        "the personal profile reads the shipped config/retrieval.json — the "
        "path that existed before the seam")
    nf = json.loads(RETRIEVAL_JSON.read_text())["not_found"]
    assert nf["enabled"] is True
    assert nf["min_rerank_score"] == -1.67  # T8 calibration vs 567-file corpus


def test_thresholds_do_not_transfer_between_profiles():
    """T8's standing rule, pinned: a threshold belongs to the score
    distribution it was derived on. The demo profile carries its OWN
    not-found gate, derived on the FastAPI corpus — if these two numbers ever
    become equal it means one corpus inherited the other's measurement."""
    import json

    from app.profile import load_profile

    demo = load_profile("demo")
    assert demo.retrieval_config is not None, "demo must not read the personal knobs"
    demo_nf = json.loads(demo.retrieval_config.read_text())["not_found"]
    personal_nf = json.loads(RETRIEVAL_JSON.read_text())["not_found"]
    assert demo_nf["min_rerank_score"] != personal_nf["min_rerank_score"]


def test_route_decision_bands_flags_and_defaults():
    from app.retrieval import route_decision
    cfg = {"routing": {"enabled": True, "escalate_band": [-1.67, 1.5],
                       "model": "frontier", "default_model": "cheap",
                       "always_frontier_questions": ["hard one?"]}}
    assert route_decision(0.98, "q", cfg) == ("frontier", "marginal-band")  # gs-024's score
    assert route_decision(1.39, "q", cfg) == ("frontier", "marginal-band")  # gs-011: the 1.5-cutoff cost
    assert route_decision(1.5, "q", cfg) == ("cheap", "default")            # upper edge exclusive
    assert route_decision(-1.67, "q", cfg) == ("frontier", "marginal-band") # lower edge inclusive
    assert route_decision(4.7, "q", cfg) == ("cheap", "default")
    assert route_decision(4.7, "hard one?", cfg) == ("frontier", "flagged")
    assert route_decision(None, "q", cfg) == ("cheap", "default")
    assert route_decision(0.98, "q", {"routing": {"enabled": False}}) == ("cheap", "default")
