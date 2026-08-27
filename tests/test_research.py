"""P3-T4 offline tests (D16 unmarked) — research pipeline pure logic:
plan parsing (brace lesson applied), synth prompt assembly (D12), gap
derivation, and the $0 critic."""
import json

import pytest

from app.research import (build_planner_prompt, build_synth_messages,
                          critic_report, derive_declared_gaps,
                          load_research_config, parse_plan)

CFG = {"min_sub_questions": 2, "max_sub_questions": 6}


# ---------- planner parse ----------

def test_parse_plan_strict_json():
    raw = json.dumps({"sub_questions": [
        {"id": "sq-1", "question": "What is X?", "rationale": "core"},
        {"id": "sq-2", "question": "What is Y?", "rationale": "contrast"}]})
    plan = parse_plan(raw, CFG)
    assert [s["id"] for s in plan["sub_questions"]] == ["sq-1", "sq-2"]


def test_parse_plan_survives_prose_wrapper_and_inner_braces():
    """The judge brace lesson, applied at birth: greedy span — a
    rationale containing `{...}` must not truncate the parse."""
    raw = ('Here is the plan:\n```json\n{"sub_questions": [{"id": "sq-1", '
           '"question": "How does action={fn} work?", "rationale": "JSX"}, '
           '{"id": "sq-2", "question": "What is Y?"}]}\n```')
    plan = parse_plan(raw, CFG)
    assert "action={fn}" in plan["sub_questions"][0]["question"]


def test_parse_plan_fails_loudly():
    with pytest.raises(ValueError, match="no JSON"):
        parse_plan("I could not produce a plan.", CFG)
    with pytest.raises(ValueError, match="outside"):
        parse_plan(json.dumps({"sub_questions": [
            {"id": f"sq-{i}", "question": f"q{i}"} for i in range(7)]}), CFG)
    with pytest.raises(ValueError, match="outside"):
        parse_plan(json.dumps({"sub_questions": [
            {"id": "sq-1", "question": "only one"}]}), CFG)
    with pytest.raises(ValueError, match="blank"):
        parse_plan(json.dumps({"sub_questions": [
            {"id": "sq-1", "question": "ok"},
            {"id": "sq-2", "question": "  "}]}), CFG)


def test_parse_plan_assigns_missing_ids():
    raw = json.dumps({"sub_questions": [{"question": "a?"},
                                        {"question": "b?"}]})
    plan = parse_plan(raw, CFG)
    assert [s["id"] for s in plan["sub_questions"]] == ["sq-1", "sq-2"]


def test_planner_prompt_carries_bounds_and_question():
    p = build_planner_prompt("How do X and Y relate?", CFG)
    assert "2-6" in p and "How do X and Y relate?" in p


def test_config_file_shape():
    cfg = load_research_config()
    assert cfg["min_sub_questions"] <= cfg["max_sub_questions"] <= 6
    assert cfg["planner_model"] == "frontier"  # ratified ruling 3
    assert cfg["synth_model"] == "frontier"


# ---------- synth assembly + gaps ----------

STEPS = [
    {"step_no": 1, "sub_question_id": "sq-1", "sub_question": "What is X?",
     "status": "done",
     "result": {"answer": "X is A [aaaa1111-0e].", "citations": ["aaaa1111-0e"],
                "retrieved": ["aaaa1111-0e", "bbbb2222-0e"], "declined": False}},
    {"step_no": 2, "sub_question_id": "sq-2", "sub_question": "What is Z?",
     "status": "done",
     "result": {"answer": "I don't know — the corpus doesn't cover this.",
                "citations": [], "retrieved": ["cccc3333-0e"],
                "declined": True}},
]


def test_synth_messages_wrap_workers_as_data():
    msgs = build_synth_messages("How do X and Z relate?", STEPS)
    assert msgs[0]["role"] == "system" and "DATA" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert user.count("<worker ") == 2 and "DECLINED" in user
    assert "X is A [aaaa1111-0e]." in user


def test_declared_gaps_carry_id_and_text():
    assert derive_declared_gaps(STEPS) == ["sq-2", "What is Z?"]


# ---------- the $0 critic ----------

def _run(brief):
    return {"steps": STEPS, "brief": brief,
            "declared_gaps": derive_declared_gaps(STEPS)}


def test_critic_clean_run():
    r = critic_report(_run("X is A [aaaa1111-0e].\n\n## Gaps\nZ is not covered."))
    assert r["clean"] and r["citations"] == ["aaaa1111-0e"]


def test_critic_catches_confabulated_id():
    r = critic_report(_run("X is A [ffff9999-0e]."))
    assert r["confabulated_citations"] == ["ffff9999-0e"]
    assert not r["clean"]


def test_critic_catches_uncovered_subquestion():
    # brief ignores sq-1's material entirely and sq-1 is not a gap
    r = critic_report(_run("Nothing useful was found."))
    assert r["uncovered_sub_questions"] == ["sq-1"]
    assert not r["clean"]


def test_generator_notfound_counts_as_declined():
    """T5 fix pin (live rs-006): a marginal-band sub-question that routes
    to a generator which honestly declines is a DECLINE, not an answer
    with zero citations — it must reach declared_gaps."""
    from types import SimpleNamespace
    from app.grounding import NOT_FOUND_ANSWER
    from app.research import step_result_from_ask
    resp = SimpleNamespace(answer=NOT_FOUND_ANSWER, citations=[],
                           retrieved=["cccc3333-0e"], gate_score=-0.83,
                           routed_to="frontier", route_reason="marginal-band",
                           trace_id="t", chunks=[])
    r = step_result_from_ask(resp)
    assert r["declined"] is True
