"""P3-T1 offline tests (D16 unmarked) — research harness pure logic.

The centerpiece is the SEEDED-FAILURE PROPERTY (SPEC-P3 §C / BLUEPRINT P3
acceptance): a run where one worker's answer was replaced by
plausible-but-uncited text, whose claim the synthesizer laundered into
the brief under another worker's citation, must PASS brief-only scoring
and FAIL the full harness — CI holds that property forever.
"""
import copy

from app.grounding import NOT_FOUND_ANSWER
from evals.research_scoring import (all_bracket_ids, brief_only_score,
                                    citation_confabulations, coverage,
                                    plan_quality, score_run, summarize,
                                    synthesis_fidelity,
                                    uncited_claim_paragraphs,
                                    union_retrieved, union_worker_citations,
                                    worker_outcomes)

# Ids in the product's real shape (uuid-ish hex, ≥8 chars per the grammar).
A, B, C, D = "aaaa1111-a", "bbbb2222-b", "cccc3333-c", "dddd4444-d"

CASE = {
    "id": "rs-fix-1",
    "question": "How do the styling methodologies in the corpus compare?",
    "must_cover": ["categories", "utility-first"],
    "must_cite_sources": [A],
    "may_cite_any": [B, C],
    "answer_must_contain": ["SMACSS"],
    "answer_must_not_contain": ["BEM is covered"],
    "expected_gaps": ["mobile styling"],
    "notes": "hand-constructed fixture, not owner ground truth",
}


def make_run() -> dict:
    """A healthy 3-worker run: two answered, one honest decline."""
    return {
        "question": CASE["question"],
        "plan": {"sub_questions": [
            {"id": "sq-1", "question": "What is SMACSS?", "rationale": "core"},
            {"id": "sq-2", "question": "What is utility-first CSS?", "rationale": "contrast"},
            {"id": "sq-3", "question": "What about mobile styling?", "rationale": "coverage"},
        ]},
        "steps": [
            {"step_no": 1, "sub_question_id": "sq-1",
             "sub_question": "What is SMACSS?", "status": "done",
             "result": {"answer": f"SMACSS sorts rules into five categories [{A}].",
                        "citations": [A], "retrieved": [A, B],
                        "gate_score": 4.1, "routed_to": "cheap",
                        "route_reason": "default", "declined": False}},
            {"step_no": 2, "sub_question_id": "sq-2",
             "sub_question": "What is utility-first CSS?", "status": "done",
             "result": {"answer": f"Utility-first composes atomic classes [{C}].",
                        "citations": [C], "retrieved": [C, D],
                        "gate_score": 2.3, "routed_to": "cheap",
                        "route_reason": "default", "declined": False}},
            {"step_no": 3, "sub_question_id": "sq-3",
             "sub_question": "What about mobile styling?", "status": "done",
             "result": {"answer": NOT_FOUND_ANSWER,
                        "citations": [], "retrieved": [D],
                        "gate_score": -2.4, "routed_to": "none",
                        "route_reason": "declined", "declined": True}},
        ],
        "brief": (
            f"# Styling methodologies\n\n"
            f"SMACSS organizes every rule into five categories [{A}].\n\n"
            f"Utility-first flattens specificity by composing atomic "
            f"classes [{C}].\n\n"
            f"## Gaps\n\nThe corpus does not cover mobile styling."
        ),
        "declared_gaps": ["sq-3", "mobile styling"],
    }


# ---------- accessors + Layer 1 ----------

def test_unions():
    run = make_run()
    assert union_retrieved(run) == {A, B, C, D}
    assert union_worker_citations(run) == {A, C}


def test_bracket_ids_unfiltered_and_ordered():
    assert all_bracket_ids(f"x [{A}] y [{D}] z [{A}]") == [A, D]


def test_confabulation_detected():
    ghost = "eeee5555-e"
    assert citation_confabulations(f"claim [{ghost}]", {A}) == [ghost]
    assert citation_confabulations(f"claim [{A}]", {A}) == []


def test_uncited_paragraphs_respect_gaps_section_and_headings():
    brief = make_run()["brief"]
    assert uncited_claim_paragraphs(brief) == []  # gaps prose exempt
    assert uncited_claim_paragraphs("A bare claim with no citation.")


def test_healthy_run_passes_everything():
    row = score_run(CASE, make_run())
    assert row["passed_brief_only"] and row["passed"], row


# ---------- case-level checks ----------

def test_must_contain_case_insensitive_and_traps():
    run = make_run()
    bad_case = dict(CASE, answer_must_contain=["smacss"],  # R1: case-insensitive
                    answer_must_not_contain=["five categories"])
    b = brief_only_score(bad_case, run["brief"], union_retrieved(run))
    assert any("must_not_contain" in f for f in b["failures"])
    assert not any("must_contain missing" in f for f in b["failures"])


def test_expected_gap_must_be_declared():
    run = make_run()
    run["declared_gaps"] = ["sq-3"]  # id kept, text dropped
    run["brief"] = run["brief"].split("## Gaps")[0].strip()  # gaps section gone
    row = score_run(CASE, run)
    assert any("expected gap not declared" in f
               for f in row["trajectory_failures"])


# ---------- trajectory checks ----------

def test_plan_quality_cap_blank_duplicate():
    run = make_run()
    subs = run["plan"]["sub_questions"]
    assert plan_quality(run) == []
    assert plan_quality(run, max_sub_questions=2)  # cap breach
    subs.append({"id": "sq-4", "question": "What is SMACSS?"})
    assert any("duplicate" in f for f in plan_quality(run))
    subs.append({"id": "sq-5", "question": "  "})
    assert any("blank" in f for f in plan_quality(run))


def test_worker_decline_shape_enforced():
    run = make_run()
    run["declared_gaps"] = []  # decline no longer carried into gaps
    assert any("not in declared_gaps" in f for f in worker_outcomes(run))
    run2 = make_run()
    run2["steps"][2]["result"]["answer"] = "Actually here's a guess."
    assert any("non-canonical" in f for f in worker_outcomes(run2))


def test_worker_citing_unretrieved_id_caught():
    run = make_run()
    run["steps"][0]["result"]["citations"] = [A, D]  # D never retrieved by sq-1
    assert any("never retrieved" in f for f in worker_outcomes(run))


def test_coverage_unaddressed_subquestion_caught():
    run = make_run()
    # brief drops the utility-first claim: sq-2 neither cited nor a gap
    run["brief"] = (f"# Styling methodologies\n\n"
                    f"SMACSS organizes every rule into five categories [{A}].\n\n"
                    f"## Gaps\n\nThe corpus does not cover mobile styling.")
    row = score_run(CASE, run)
    assert any("sq-2" in f for f in row["trajectory"]["coverage"])


def test_synthesis_fidelity_reaching_past_workers_caught():
    run = make_run()
    # B was retrieved by worker 1 but no worker CITED it; brief cites it
    run["brief"] += f"\n\nAn extra claim from raw retrieval [{B}]."
    assert synthesis_fidelity(run, run["brief"])


# ---------- THE seeded-failure property (BLUEPRINT P3 acceptance) ----------

def make_seeded_run() -> dict:
    """Worker sq-2's answer replaced by plausible-but-UNCITED text; the
    synthesizer launders its claim into the brief by dressing it with a
    RAW RETRIEVED id no worker's answer ever cited. The brief alone looks
    perfect: every citation is in the retrieved union, every case check
    passes."""
    run = copy.deepcopy(make_run())
    run["steps"][1]["result"]["answer"] = (
        "Utility-first composes atomic classes and flattens specificity.")
    run["steps"][1]["result"]["citations"] = []          # the seed
    run["brief"] = (
        f"# Styling methodologies\n\n"
        f"SMACSS organizes every rule into five categories [{A}].\n\n"
        f"Utility-first flattens specificity by composing atomic "
        f"classes [{C}].\n\n"    # laundered: C retrieved, never worker-cited
        f"## Gaps\n\nThe corpus does not cover mobile styling.")
    return run


def test_seeded_failure_slips_past_brief_only_scoring():
    run = make_seeded_run()
    b = brief_only_score(CASE, run["brief"], union_retrieved(run))
    assert b["passed"], b  # final-output-only evaluation is blind to it


def test_seeded_failure_caught_by_trajectory():
    row = score_run(CASE, make_seeded_run())
    assert row["passed_brief_only"] is True
    assert row["passed"] is False
    assert any("ZERO citations" in f
               for f in row["trajectory"]["worker_outcomes"])
    assert any("sq-2" in f for f in row["trajectory"]["coverage"])


def test_summarize_reports_the_catch():
    rows = [score_run(CASE, make_run()), score_run(CASE, make_seeded_run())]
    s = summarize(rows)
    assert s == {"cases_total": 2, "cases_passed": 1, "pass_rate": 0.5,
                 "passed_brief_only": 2, "trajectory_catches": 1}


def test_uncited_check_exempts_markdown_rules_not_prose():
    """T4 live false-positive pin: horizontal rules are structure, not
    claims — but genuinely uncited prose still fails."""
    brief = (f"# Title\n\nA cited claim [{A}].\n\n---\n\n"
             f"An uncited prose claim.\n\n***\n\n## Gaps\n\nnothing")
    flagged = uncited_claim_paragraphs(brief)
    assert flagged == ["An uncited prose claim."]


def test_uncited_exemptions_leadin_and_table_fragment():
    """T5 live-calibration pins: colon lead-in followed by a cited
    paragraph, and a data-less table fragment, are structure — but an
    uncited lead-in followed by UNCITED content still fails, and a table
    with uncited DATA rows still fails."""
    ok = (f"Four mechanisms are identified:\n\n- first [{A}]\n- second [{B}]\n\n"
          f"| Col1 | Col2 |\n|---|---|")
    assert uncited_claim_paragraphs(ok) == []
    bad_leadin = "Four mechanisms are identified:\n\nAn uncited list follows."
    assert len(uncited_claim_paragraphs(bad_leadin)) == 2
    bad_table = f"| Layer | Role |\n|---|---|\n| short-term | window |"
    assert uncited_claim_paragraphs(bad_table)


def test_gap_class_satisfiability_proposal():
    """T6 proposal pin: an all-declined run with honest gap declaration
    satisfies a guard-class case even though nothing is cited —
    may_cite_any is N/A. Strict (pre-proposal) verdict still reported.
    A PARTIALLY-declined run gets no waiver."""
    from app.grounding import NOT_FOUND_ANSWER
    case = {"id": "rs-g", "question": "mobile?", "must_cover": [],
            "may_cite_any": ["aaaa1111-0e"], "answer_must_contain": [],
            "answer_must_not_contain": [], "expected_gaps": ["mobile"]}
    run = {"question": "mobile?",
           "plan": {"sub_questions": [{"id": "sq-1", "question": "Flutter in KB?"}]},
           "steps": [{"step_no": 1, "sub_question_id": "sq-1",
                      "sub_question": "Flutter in KB?", "status": "done",
                      "result": {"answer": NOT_FOUND_ANSWER, "citations": [],
                                 "retrieved": ["aaaa1111-0e"], "declined": True}}],
           "brief": "## Gaps\n\nThe corpus does not cover mobile.",
           "declared_gaps": ["sq-1", "Flutter in KB?", "mobile"]}
    row = score_run(case, run)
    assert row["passed"] is True          # proposed semantics
    assert row["passed_strict"] is False  # pre-proposal reading, reported
    assert row["waived_by_gap_semantics"]
    # partial decline: waiver must NOT apply
    import copy
    run2 = copy.deepcopy(run)
    run2["plan"]["sub_questions"].append({"id": "sq-2", "question": "adjacent?"})
    run2["steps"].append({"step_no": 2, "sub_question_id": "sq-2",
                          "sub_question": "adjacent?", "status": "done",
                          "result": {"answer": f"Adjacent [bbbb2222-0e].",
                                     "citations": ["bbbb2222-0e"],
                                     "retrieved": ["bbbb2222-0e"], "declined": False}})
    run2["brief"] = f"Adjacent web material exists [bbbb2222-0e].\n\n## Gaps\n\nmobile"
    row2 = score_run(case, run2)
    assert not row2["waived_by_gap_semantics"]
