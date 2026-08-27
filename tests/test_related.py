"""Offline tests for /related pure logic (P2-T1, D16 unmarked):
source aggregation and verdict bands."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.retrieval import aggregate_sources, related_verdict  # noqa: E402

ROWS = [
    {"source_id": "aaa", "title": "Doc A", "source_table": "EmKb", "similarity": 0.7},
    {"source_id": "aaa", "title": "Doc A", "source_table": "EmKb", "similarity": 0.9},
    {"source_id": "bbb", "title": "Doc B", "source_table": "EmSession", "similarity": 0.6},
]


def test_aggregate_rolls_chunks_to_sources_keeping_best():
    out = aggregate_sources(ROWS, [1.0, 3.0, 2.0])
    assert [s["source_id"] for s in out] == ["aaa", "bbb"]  # by best CE desc
    a = out[0]
    assert a["chunk_hits"] == 2
    assert a["best_rerank_score"] == 3.0 and a["best_similarity"] == 0.9


def test_aggregate_respects_top_k_and_empty():
    assert len(aggregate_sources(ROWS, [1.0, 2.0, 3.0], top_k=1)) == 1
    assert aggregate_sources([], []) == []


CFG = {"related_bands": {"covered_min": 0.0, "adjacent_min": -4.0}}


def test_verdict_bands_calibrated_for_topic_shape():
    # spot-check anchors (2026-07-14): covered min +4.19, absent max -5.47
    assert related_verdict(4.19, CFG) == "likely covered"
    assert related_verdict(0.0, CFG) == "likely covered"      # boundary
    assert related_verdict(-2.0, CFG) == "adjacent material"
    assert related_verdict(-4.0, CFG) == "adjacent material"  # boundary
    assert related_verdict(-5.47, CFG) == "nothing close"
    assert related_verdict(None, CFG) == "unknown"
