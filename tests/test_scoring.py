"""Offline tests for evals/scoring.py (D16 unmarked) — completes the
salvaged P1-T5 worker's definition of done (worker died on the credit cap
before writing these; math verified here matches its docstrings and the T4
rulings R1/R2)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))

from scoring import (  # noqa: E402
    context_precision,
    context_recall,
    is_answerable,
    layer1_failures,
    relevant_ids,
)

ANSWERABLE = {
    "id": "x", "type": "ask",
    "must_cite_sources": ["aaa"],
    "may_cite_any": ["bbb", "ccc"],
    "answer_must_contain": ["One dimension"],
    "answer_must_not_contain": ["fabricated"],
}
GUARD = {"id": "g", "type": "ask_notfound", "expected_behavior": "not_found"}


def test_relevant_ids_unions_both_fields_and_empty_for_guards():
    assert relevant_ids(ANSWERABLE) == {"aaa", "bbb", "ccc"}
    assert relevant_ids(GUARD) == set()


def test_context_precision_counts_relevant_chunks_with_repeats():
    assert context_precision(["aaa", "aaa", "zzz", "bbb", "qqq"], {"aaa", "bbb"}) == 0.6
    assert context_precision([], {"aaa"}) == 0.0


def test_context_recall_must_cite_is_fraction_of_required():
    case = {"must_cite_sources": ["aaa", "ddd"]}
    assert context_recall(["aaa", "zzz"], case) == 0.5
    assert context_recall(["aaa", "ddd"], case) == 1.0


def test_context_recall_may_cite_any_is_binary_and_must_takes_precedence():
    assert context_recall(["ccc"], {"may_cite_any": ["bbb", "ccc"]}) == 1.0
    assert context_recall(["zzz"], {"may_cite_any": ["bbb", "ccc"]}) == 0.0
    # when both fields exist, must_cite_sources drives recall (harder contract)
    assert context_recall(["bbb"], ANSWERABLE) == 0.0


def test_is_answerable_flags_guards_only():
    assert is_answerable(ANSWERABLE) and not is_answerable(GUARD)


def test_layer1_case_insensitive_matching_r1():
    # R1: "one dimension" satisfies "One dimension"; forbidden check too
    fails = layer1_failures(ANSWERABLE, "covers one dimension fine", ["aaa", "bbb"], 0.8)
    assert fails == []
    fails = layer1_failures(ANSWERABLE, "one dimension but FABRICATED", ["aaa", "bbb"], 0.8)
    assert any("forbidden" in f for f in fails)


def test_layer1_citation_contracts():
    missing_must = layer1_failures(ANSWERABLE, "one dimension", ["bbb"], 0.8)
    assert any("missing required citation: aaa" in f for f in missing_must)
    missing_any = layer1_failures(ANSWERABLE, "one dimension", ["aaa"], 0.8)
    assert any("may_cite_any" in f for f in missing_any)


def test_layer1_guard_accepts_decline_phrasing_or_low_confidence():
    assert layer1_failures(GUARD, "I don't know — the corpus doesn't cover this.", [], 0.61) == []
    assert layer1_failures(GUARD, "That was not found in the corpus.", [], 0.9) == []
    assert layer1_failures(GUARD, "anything", [], 0.3) == []      # low confidence
    fails = layer1_failures(GUARD, "Here is a confident answer!", [], 0.9)
    assert len(fails) == 1 and "expected not-found" in fails[0]
