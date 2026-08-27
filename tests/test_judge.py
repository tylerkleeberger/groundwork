"""Offline tests for evals/judge.py pure logic (D16 unmarked): prompt
assembly, score parsing, calibration agreement math. No network."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))

from judge import (  # noqa: E402
    build_judge_prompt,
    calibration_agreement,
    format_chunks,
    parse_score,
)

CHUNKS = [
    {"source_id": "aaa", "title": "Doc A", "section": "S1",
     "similarity": 0.9, "content": "Alpha content."},
    {"source_id": "bbb", "title": None, "section": "",
     "similarity": 0.7, "content": "Beta content."},
]


def test_format_chunks_labels_and_separators():
    out = format_chunks(CHUNKS)
    assert "[aaa] Doc A — S1\nAlpha content." in out
    assert "[bbb]\nBeta content." in out
    assert "\n\n---\n\n" in out
    assert format_chunks([]) == "(no chunks retrieved)"


def test_build_judge_prompt_fills_all_slots_both_rubrics():
    for rubric in ("faithfulness", "relevancy"):
        p = build_judge_prompt(rubric, "Q?", "A.", CHUNKS)
        assert "Q?" in p and "A." in p and "[aaa] Doc A" in p
        assert "{question}" not in p and "{answer}" not in p and "{chunks}" not in p
        assert '{"score"' in p  # response contract present in rubric


def test_parse_score_plain_and_wrapped():
    assert parse_score('{"score": 0.75, "rationale": "ok"}') == (0.75, "ok")
    s, r = parse_score('Sure! Here is my grade:\n{"score": 1, "rationale": "grounded"}\nDone.')
    assert s == 1.0 and r == "grounded"


def test_parse_score_rejects_garbage_and_out_of_range():
    with pytest.raises(ValueError):
        parse_score("I think it deserves a good grade.")
    with pytest.raises(ValueError):
        parse_score('{"score": 7, "rationale": "confused"}')


def test_calibration_agreement_math(tmp_path, monkeypatch):
    import judge as judge_mod
    labels = {"gs-001": {"faithfulness": 1.0, "relevancy": 1.0},
              "gs-026": {"faithfulness": 1.0, "relevancy": 0.5}}
    f = tmp_path / "calibration.json"
    f.write_text(json.dumps({"labels": labels, "constructed": []}))
    monkeypatch.setattr(judge_mod, "CALIBRATION_FILE", f)
    records = [
        {"id": "gs-001", "faithfulness": 0.75, "relevancy": 1.0},   # diffs .25, 0
        {"id": "gs-026", "faithfulness": 1.0, "relevancy": 1.0},    # diffs 0, .5
        {"id": "gs-002", "faithfulness": 0.5, "relevancy": 0.5},    # unlabeled: ignored
        {"id": "gs-003"},                                           # unjudged: ignored
    ]
    agg = calibration_agreement(records)
    assert agg["labeled_cases_in_run"] == 2
    assert agg["mean_abs_diff"] == round((0.25 + 0 + 0 + 0.5) / 4, 4)
    assert agg["within_tolerance_rate"] == 0.75  # 3 of 4 diffs <= 0.25
    assert agg["per_case"]["gs-026"]["relevancy"]["abs_diff"] == 0.5


def test_calibration_agreement_none_without_labels(monkeypatch, tmp_path):
    import judge as judge_mod
    monkeypatch.setattr(judge_mod, "CALIBRATION_FILE", tmp_path / "missing.json")
    assert calibration_agreement([{"id": "x", "faithfulness": 1.0, "relevancy": 1.0}]) is None


def test_parse_score_survives_inner_braces_in_rationale():
    """P3-T3 regression pin: a rationale containing `{...}` (the live
    gs-016 shape — the judge wrote React's `action={fn}`) must parse via
    the greedy fallback instead of erroring as unparseable."""
    raw = ('```json\n{\n  "score": 1.0,\n  "rationale": "Form Actions '
           'with action={fn} and useFormStatus are supported."\n}\n```')
    score, rationale = parse_score(raw)
    assert score == 1.0 and "action={fn}" in rationale
