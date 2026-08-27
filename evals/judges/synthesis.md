# Judge rubric: synthesis quality (0–1) — research briefs (P3-T1 draft)

You are grading the SYNTHESIS of a multi-source research brief produced
by an orchestrator-worker system. Other layers already check grounding
(the faithfulness judge, run with answer = brief and chunks = the union
of worker chunks) and citation validity (deterministic). Your only
questions are the three below — do not re-grade grounding or citation
form (the T6 lesson: one metric must never bleed into another).

Score each dimension 0–1 (0.25 steps fine), report all three and their
mean as the composite:

**1. Coverage.** Does the brief address the research question's required
themes (the case's must_cover list, shown to you)? A theme addressed in
one grounded sentence counts; a theme silently absent does not. Themes
the brief EXPLICITLY declares as corpus gaps count as addressed-honestly
(grade gap honesty separately, below).

**2. Conflict handling.** Where sources disagree, the brief must SURFACE
the disagreement ("source X says A; source Y says B"), never silently
average, blend, or pick a side without saying so. If the inputs contain
no conflict, score 1.0 and note "no conflict present."

**3. Gap honesty.** Aspects the corpus cannot answer must be DECLARED
(a gaps section or explicit in-text statement), never improvised or
papered over with adjacent-but-off-target material. A declared gap that
is actually covered by the workers' answers is also a defect (false
modesty hides coverage) — score it down.

Special cases:
- A brief that is one giant declared gap (nothing answerable) scores 1.0
  on gap honesty and is graded on coverage only if the case says some
  themes WERE answerable.
- Style, length, and eloquence are NOT graded.

Output STRICT JSON (the judge.py parse contract):
{"coverage": <0-1>, "conflict_handling": <0-1>, "gap_honesty": <0-1>,
 "composite": <mean>, "rationale": "<one paragraph>"}

---

## Anchor-set plan (T1 deliverable — ready for owner labeling)

Per the frozen-anchor protocol (T7 lesson: anchors FROZEN so agreement
measures judge movement alone):

- **5 real anchors:** the first research briefs the T4 pipeline produces
  over the certified rs-cases — director labels all three dimensions,
  owner ratifies (the T6 flow; labels are ground truth, the rubric moves,
  never the labels).
- **2 constructed negatives (drafted with the anchors, before any
  calibration run):**
  - *uncited-synthesis negative* — a brief weaving claims no worker
    produced (targets coverage=looks-fine, fidelity-defect shape; the
    judge should still see coverage but the composite must not mask it —
    this negative calibrates dimension independence);
  - *papered-over-gap negative* — a brief that answers an expected_gaps
    aspect from adjacent material instead of declaring it (targets gap
    honesty 0.0–0.25).
- Agreement metric: mean_abs_diff + within-0.25 rate per dimension,
  reported per run exactly as the faithfulness/relevancy calibration
  block does today.
- Labeling sheet: evals/judges/calibration_sheet.md pattern — one block
  per anchor, three blanks per block, owner fills or one-words the
  director's labels per the standing adjudication split.
