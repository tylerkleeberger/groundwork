"""Offline tests for the P2-T2 feedback loop pure logic (D16 unmarked):
flag snapshot round-trip, candidate assembly, verdict application."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from adjudicate import (  # noqa: E402
    apply_verdict,
    is_adjudicated,
    make_candidate,
    render_flag,
)

FLAG = {
    "flagged_at": "2026-07-14T15:00:00", "reason": "cited wrong doc",
    "question": "What did I capture about closures?",
    "answer": "Closures are …", "citations": ["aaa"], "retrieved": ["aaa", "bbb"],
    "chunks": [{"source_id": "aaa", "title": "Doc A"}],
    "gate_score": 2.5, "confidence": 0.8,
}


def test_flag_carries_question_for_cross_terminal_visibility():
    # T2 gate amendment (b): the question rides the flag so a global-last
    # mix-up is visible at adjudication, not silent
    assert "closures" in render_flag(FLAG)
    assert FLAG["question"] in render_flag(FLAG)


def test_candidate_is_clearly_marked_and_never_a_case():
    c = make_candidate(FLAG, "golden", note="verify source first")
    assert "NOT in the golden set" in c["_status"]
    assert c["_kind"] == "golden"
    assert c["_flag"]["question"] == FLAG["question"]
    assert "must_cite_sources_SUGGESTION" in c
    t = make_candidate(FLAG, "trap", None)
    assert "answer_must_not_contain_SUGGESTION" in t


def test_verdict_appends_without_destroying_snapshot():
    out = apply_verdict(FLAG, "dismissed", "actually correct")
    assert is_adjudicated(out) and not is_adjudicated(FLAG)
    assert out["verdict"]["kind"] == "dismissed"
    assert out["answer"] == FLAG["answer"]  # snapshot intact


def test_flag_file_round_trip(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps(FLAG))
    loaded = json.loads(p.read_text())
    assert loaded == FLAG
