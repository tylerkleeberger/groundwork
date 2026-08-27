"""Offline tests for app/reranker.py score-ordering logic (D16 unmarked).
The ONNX session itself is exercised by the live suite."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.reranker import top_k_by_score  # noqa: E402
from app.retrieval import load_retrieval_config  # noqa: E402


def test_orders_by_descending_score():
    assert top_k_by_score(["a", "b", "c"], [0.1, 0.9, 0.5], k=3) == ["b", "c", "a"]


def test_takes_exactly_k():
    assert top_k_by_score(["a", "b", "c", "d"], [4, 3, 2, 1], k=2) == ["a", "b"]


def test_ties_break_by_fused_position_deterministically():
    # equal scores → original (RRF) order wins; stable across runs
    assert top_k_by_score(["x", "y", "z"], [0.5, 0.5, 0.5], k=2) == ["x", "y"]


def test_k_larger_than_input_returns_all():
    assert top_k_by_score(["a", "b"], [1.0, 2.0], k=10) == ["b", "a"]


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        top_k_by_score(["a"], [1.0, 2.0], k=1)


def test_reranker_config_is_pinned_and_enabled():
    rr = load_retrieval_config()["reranker"]
    assert rr["enabled"] is True
    assert rr["model_repo"] == "Xenova/ms-marco-MiniLM-L-6-v2"
    assert rr["model_file"] == "onnx/model_quantized.onnx"  # int8: delta measured
    assert rr["candidates"] >= 50
