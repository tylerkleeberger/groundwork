"""P3-T1 research eval harness — pure scoring logic (D16 unmarked, offline).

Scores a research RUN RECORD (the §B checkpoint shape: plan + step rows +
brief + declared gaps) against a research case (evals/research_set.jsonl,
schema below). Built BEFORE the pipeline exists (SPEC-P3 §C eval-first
order): the first brief ever generated is scored by machinery that
predates it. No I/O here — the runner layer (T4) owns HTTP/DB and file
emission, exactly as scoring.py/test_evals.py split for Ask.

Case schema (rs-xxx, owner-certified via the fenced method, same
do-not-touch standing as golden_set.jsonl):
  { id, question,
    must_cover: [themes the brief must address],
    must_cite_sources: [...], may_cite_any: [...],   # union-level, R1/T4 semantics
    answer_must_contain: [...], answer_must_not_contain: [...],  # case-insensitive (R1)
    expected_gaps: [aspects the corpus genuinely lacks — must be DECLARED],
    notes }

Run record contract (produced by the T4 pipeline from research_runs +
research_steps; hand-constructable for fixtures):
  { question, plan: {sub_questions: [{id, question, rationale}]},
    steps: [{step_no, sub_question_id, sub_question, status,
             result: {answer, citations, retrieved, gate_score,
                      routed_to, route_reason, declined}}],
    brief, declared_gaps: [sub_question ids] }

Two scoring surfaces, deliberately separate (the seeded-failure property
in SPEC-P3 §C hangs on the distinction):
  brief_only_score()  — what final-output-only evaluation can see:
                        (case, brief, union of retrieved ids) and nothing
                        else. The strawman being beaten.
  score_run()         — the real harness: brief checks PLUS trajectory
                        checks over plan and step rows. Catches the
                        laundered-claim worker failure brief_only misses.
"""
from __future__ import annotations

# One citation grammar, one home: app/grounding.py owns the bracket-form
# regex (plain [id] + markdown-link form, T7 ruling). Importing the
# module-private pattern is deliberate — a copied regex here WOULD drift
# from the product's the day one of them changes. tests pin the coupling.
from app.grounding import _CITATION, NOT_FOUND_ANSWER, extract_citations

DEFAULT_MAX_SUB_QUESTIONS = 6


# ---------- run-record accessors ----------

def union_retrieved(run: dict) -> set[str]:
    """Union of every worker's retrieved ids — the allowed-citation set
    for the whole run (§A critic: the existing confabulation defense,
    one parameter wider)."""
    out: set[str] = set()
    for step in run.get("steps", []):
        out |= set((step.get("result") or {}).get("retrieved", []))
    return out


def union_worker_citations(run: dict) -> set[str]:
    """Union of ids the workers actually cited — the traceability set
    for synthesis fidelity (brief claims must come from worker answers,
    not directly from retrieval the synthesizer never saw)."""
    out: set[str] = set()
    for step in run.get("steps", []):
        out |= set((step.get("result") or {}).get("citations", []))
    return out


def all_bracket_ids(text: str) -> list[str]:
    """Every citation-form id in the text, UNFILTERED, deduped in order —
    the raw material for confabulation detection (extract_citations
    filters to an allowed set and so cannot report what was invented)."""
    seen: list[str] = []
    for m in _CITATION.finditer(text or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


# ---------- Layer 1: brief-level checks (final-output-visible) ----------

def citation_confabulations(brief: str, allowed: set[str]) -> list[str]:
    """Bracket ids in the brief that no worker retrieved — each one is a
    confabulation defect. PRESERVED PROPERTY (SPEC-P3 §C): only
    retrieval-provided ids pass, exactly as in Ask."""
    return [cid for cid in all_bracket_ids(brief) if cid not in allowed]


def _paragraphs(brief: str) -> list[str]:
    return [p.strip() for p in (brief or "").split("\n\n") if p.strip()]


def _is_table_structure_only(para: str) -> bool:
    """A table fragment with no data rows (header + separator, split
    from its body by a blank line) is structure, not claims."""
    lines = [l.strip() for l in para.splitlines() if l.strip()]
    if not lines or not all(l.startswith("|") for l in lines):
        return False
    data = [l for l in lines if set(l) - set("|-: ")]
    return len(data) <= 1  # header row only (or nothing but separators)


def uncited_claim_paragraphs(brief: str) -> list[str]:
    """Claim-bearing paragraphs with zero citations. Structural
    definition (§C): prose paragraphs outside the declared-gaps section;
    headings are not claims. The gaps section starts at the first heading
    containing 'gap' (case-insensitive) and runs to the end.

    Two live-calibrated structure exemptions (T5, each pinned offline;
    'structure is not a claim' is the ratified principle):
    - a colon-terminated LEAD-IN whose immediately following paragraph
      carries a citation (the claims live in the cited continuation);
    - a table fragment with no data rows (header split from its body).
    Uncited PROSE and uncited table DATA rows still fail."""
    out: list[str] = []
    in_gaps = False
    paras = _paragraphs(brief)
    for i, para in enumerate(paras):
        first_line = para.splitlines()[0]
        if first_line.lstrip().startswith("#"):
            if "gap" in first_line.lower():
                in_gaps = True
            continue
        if in_gaps:
            continue
        # markdown structure is not a claim: horizontal rules (---/***/___)
        # were counted as uncited prose on the first live briefs (T4
        # false-positive, 4-13 hits per brief) — structure is exempt,
        # genuinely uncited prose still fails (pinned offline)
        if set(para) <= set("-*_ \n"):
            continue
        if _is_table_structure_only(para):
            continue
        if (para.rstrip().endswith(":") and i + 1 < len(paras)
                and all_bracket_ids(paras[i + 1])):
            continue  # lead-in; its claims are in the cited continuation
        if not all_bracket_ids(para):
            out.append(para[:80])
    return out


def case_string_checks(case: dict, brief: str) -> list[str]:
    """answer_must_contain / answer_must_not_contain, case-insensitive
    (R1 semantics carried from the Ask exam). Returns failure strings."""
    low = (brief or "").lower()
    fails = []
    for s in case.get("answer_must_contain", []):
        if s.lower() not in low:
            fails.append(f"must_contain missing: {s!r}")
    for s in case.get("answer_must_not_contain", []):
        if s.lower() in low:
            fails.append(f"must_not_contain present: {s!r}")
    return fails


def case_citation_checks(case: dict, brief_cited: list[str]) -> list[str]:
    """must_cite_sources = ALL required; may_cite_any = ANY ONE (T4
    rulings, union-level for research)."""
    got = set(brief_cited)
    fails = []
    for sid in case.get("must_cite_sources", []):
        if sid not in got:
            fails.append(f"must_cite missing: {sid}")
    any_of = case.get("may_cite_any", [])
    if any_of and not (got & set(any_of)):
        fails.append(f"may_cite_any: none of {len(any_of)} present")
    return fails


def brief_only_score(case: dict, brief: str, allowed: set[str]) -> dict:
    """Everything a final-output-only evaluator can check: the brief, the
    union retrieved set, and the case. Deliberately blind to plan/steps —
    this is the surface the seeded-failure fixture must slip past."""
    cited = extract_citations(brief, sorted(allowed))
    failures = []
    confab = citation_confabulations(brief, allowed)
    if confab:
        failures.append(f"confabulated citations: {confab}")
    uncited = uncited_claim_paragraphs(brief)
    if uncited:
        failures.append(f"uncited claim paragraphs: {len(uncited)}")
    failures += case_string_checks(case, brief)
    failures += case_citation_checks(case, cited)
    return {"citations": cited, "failures": failures,
            "passed": not failures}


# ---------- Trajectory checks (step-level; DIRECTION §3) ----------

def plan_quality(run: dict,
                 max_sub_questions: int = DEFAULT_MAX_SUB_QUESTIONS) -> list[str]:
    """Structural plan checks: non-empty, within cap, unique, no blanks.
    (Semantic decomposition quality is the judge's job, not this one.)"""
    subs = (run.get("plan") or {}).get("sub_questions", [])
    fails = []
    if not subs:
        fails.append("plan: zero sub-questions")
    if len(subs) > max_sub_questions:
        fails.append(f"plan: {len(subs)} sub-questions exceeds cap {max_sub_questions}")
    texts = [(s.get("question") or "").strip().lower() for s in subs]
    if any(not t for t in texts):
        fails.append("plan: blank sub-question")
    if len(set(texts)) != len(texts):
        fails.append("plan: duplicate sub-questions")
    return fails


def worker_outcomes(run: dict) -> list[str]:
    """Per-step honesty checks — the seeded-failure catcher:
    - a DECLINED step must look declined (canonical answer, zero
      citations) and be carried into declared_gaps;
    - an ANSWERED step must cite ≥1 id, and only ids it retrieved
      (a worker citing what it never saw is the Ask confabulation
      defense applied per-worker)."""
    gaps = set(run.get("declared_gaps", []))
    fails = []
    for step in run.get("steps", []):
        sid = step.get("sub_question_id", f"step-{step.get('step_no')}")
        r = step.get("result") or {}
        if step.get("status") != "done":
            fails.append(f"{sid}: status {step.get('status')!r} (run incomplete)")
            continue
        if r.get("declined"):
            if r.get("citations"):
                fails.append(f"{sid}: declined but cites {r['citations']}")
            if r.get("answer") != NOT_FOUND_ANSWER:
                fails.append(f"{sid}: declined with non-canonical answer")
            if sid not in gaps:
                fails.append(f"{sid}: declined but not in declared_gaps")
        else:
            cits = r.get("citations", [])
            if not cits:
                fails.append(f"{sid}: answered with ZERO citations")
            bad = [c for c in cits if c not in set(r.get("retrieved", []))]
            if bad:
                fails.append(f"{sid}: cites ids it never retrieved: {bad}")
    return fails


def coverage(run: dict, brief_cited: list[str]) -> list[str]:
    """Every planned sub-question is addressed in the brief or declared a
    gap (§A critic). 'Addressed' is deterministic: the brief cites at
    least one id from that worker's citation set — the same traceability
    the synthesis-fidelity check uses."""
    gaps = set(run.get("declared_gaps", []))
    step_by_id = {s.get("sub_question_id"): s for s in run.get("steps", [])}
    got = set(brief_cited)
    fails = []
    for sub in (run.get("plan") or {}).get("sub_questions", []):
        sid = sub.get("id")
        if sid in gaps:
            continue
        step = step_by_id.get(sid)
        cits = set(((step or {}).get("result") or {}).get("citations", []))
        if not (got & cits):
            fails.append(f"{sid}: neither addressed in brief nor declared a gap")
    return fails


def synthesis_fidelity(run: dict, brief: str) -> list[str]:
    """Brief claims must trace to worker ANSWERS, not around them: every
    brief citation must appear in some worker's citation set. An id that
    was retrieved but never cited by any worker reaching the brief means
    the synthesizer reached past its inputs (§C: each claim traceable to
    a specific worker's answer, checked via the citation sets)."""
    traceable = union_worker_citations(run)
    return [f"brief cites {cid} — retrieved but no worker's answer cites it"
            for cid in all_bracket_ids(brief)
            if cid in union_retrieved(run) and cid not in traceable]


def expected_gaps_check(case: dict, run: dict, brief: str) -> list[str]:
    """Gap honesty at case level: each expected_gaps aspect must surface
    in declared gaps or the brief's gaps section, never be silently
    filled. Substring match, case-insensitive (R1 spirit)."""
    declared = " ".join(str(g) for g in run.get("declared_gaps", [])).lower()
    gaps_text = ""
    in_gaps = False
    for para in _paragraphs(brief):
        first = para.splitlines()[0]
        if first.lstrip().startswith("#") and "gap" in first.lower():
            in_gaps = True
            continue
        if in_gaps:
            gaps_text += para.lower() + "\n"
    fails = []
    for aspect in case.get("expected_gaps", []):
        if aspect.lower() not in declared and aspect.lower() not in gaps_text:
            fails.append(f"expected gap not declared: {aspect!r}")
    return fails


# ---------- end-to-end ----------

def all_workers_declined(run: dict) -> bool:
    """True when every planned step honestly declined — the total-gap
    outcome a guard-class research case exists to elicit."""
    steps = run.get("steps", [])
    return bool(steps) and all((s.get("result") or {}).get("declined")
                               for s in steps)


def score_run(case: dict, run: dict,
              max_sub_questions: int = DEFAULT_MAX_SUB_QUESTIONS) -> dict:
    """The full harness: brief-level Layer 1 + trajectory checks, one
    results row. Cost/judge columns are joined by the runner (T4/T5) —
    this module stays pure and offline.

    Gap-class satisfiability (T6 proposal, ratification-gated at the
    phase gate): when ALL workers honestly declined and the gap checks
    hold, `may_cite_any` is N/A — an honest total-gap brief cites
    nothing, and requiring a citation makes the guard-class case
    unsatisfiable by its own correct outcome. Both scorings are
    reported (`passed` = proposed semantics; `passed_strict` = the
    pre-proposal reading) until the chain closes."""
    allowed = union_retrieved(run)
    brief = run.get("brief") or ""
    b = brief_only_score(case, brief, allowed)
    waived = []
    if all_workers_declined(run):
        waived = [f for f in b["failures"] if f.startswith("may_cite_any")]
        b = dict(b, failures=[f for f in b["failures"] if f not in waived])
    trajectory = {
        "plan_quality": plan_quality(run, max_sub_questions),
        "worker_outcomes": worker_outcomes(run),
        "coverage": coverage(run, b["citations"]),
        "synthesis_fidelity": synthesis_fidelity(run, brief),
        "expected_gaps": expected_gaps_check(case, run, brief),
    }
    trajectory_failures = [f for fails in trajectory.values() for f in fails]
    passed = not b["failures"] and not trajectory_failures
    return {
        "id": case.get("id"),
        "question": case.get("question"),
        "citations": b["citations"],
        "brief_failures": b["failures"],
        "waived_by_gap_semantics": waived,
        "trajectory_failures": trajectory_failures,
        "trajectory": trajectory,
        "passed_brief_only": b["passed"] and not waived,
        "passed": passed,
        "passed_strict": passed and not waived,
    }


def summarize(rows: list[dict]) -> dict:
    """Aggregates for the results file — margin-discipline style carried
    from the Ask harness: the delta between the two surfaces is itself a
    reported number (it is the trajectory layer's measured value)."""
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    brief_only = sum(1 for r in rows if r["passed_brief_only"])
    return {
        "cases_total": total,
        "cases_passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "passed_brief_only": brief_only,
        "trajectory_catches": brief_only - passed,
    }
