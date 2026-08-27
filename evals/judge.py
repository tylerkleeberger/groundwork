"""P1-T6 Layer-2 judge: faithfulness + relevancy via gateway alias `cheap`.

Rubric prompts live in evals/judges/*.md (committed artifacts — a rubric
change is a reviewable diff, and per the calibration contract it is the
RUBRIC that changes when the judge disagrees with owner labels, never the
labels). Prompt assembly and score parsing are pure and offline-tested
(tests/test_judge.py); only judge_case() touches the network.

Calibration: evals/judges/calibration.json holds owner-labeled ground truth
for 5 cases ({case_id: {faithfulness, relevancy}}). Every judged run reports
agreement (mean absolute difference + within-0.25 rate) so judge drift is
visible in the results file, run over run.
"""
from __future__ import annotations

import json
import pathlib
import re

JUDGES_DIR = pathlib.Path(__file__).parent / "judges"
CALIBRATION_FILE = JUDGES_DIR / "calibration.json"
JUDGE_ALIAS = "cheap"
AGREEMENT_TOLERANCE = 0.25

_JSON_OBJ = re.compile(r"\{.*?\}", re.DOTALL)


def format_chunks(chunks: list[dict]) -> str:
    """Render retrieved chunks for a judge prompt — same [source_id] labeling
    the generator saw, so citations in the answer stay checkable."""
    blocks = []
    for c in chunks:
        head = f"[{c['source_id']}]"
        if c.get("title"):
            head += f" {c['title']}"
        if c.get("section"):
            head += f" — {c['section']}"
        blocks.append(f"{head}\n{c['content']}")
    return "\n\n---\n\n".join(blocks) if blocks else "(no chunks retrieved)"


def build_judge_prompt(rubric: str, question: str, answer: str,
                       chunks: list[dict]) -> str:
    template = (JUDGES_DIR / f"{rubric}.md").read_text()
    return (template
            .replace("{question}", question)
            .replace("{answer}", answer)
            .replace("{chunks}", format_chunks(chunks)))


def parse_score(raw: str) -> tuple[float, str]:
    """Extract {"score", "rationale"} from a judge reply. Tolerates prose
    around the JSON. Raises ValueError on anything unusable — a judge that
    can't produce a score must be visible, not silently 0."""
    candidates = [m.group(0) for m in _JSON_OBJ.finditer(raw)]
    # P3-T3 parse fix: the non-greedy pattern truncates at the first `}`
    # INSIDE the JSON when a rationale contains inner braces (first seen
    # live on gs-016 — the judge wrote React's `action={fn}` syntax).
    # Greedy first-{-to-last-} fallback spans nested braces; scoring
    # semantics untouched — this only recovers replies that previously
    # errored as unparseable.
    if "{" in raw and "}" in raw:
        candidates.append(raw[raw.index("{"):raw.rindex("}") + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if "score" in obj:
            score = float(obj["score"])
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"judge score out of range: {score}")
            return round(score, 4), str(obj.get("rationale", ""))
    raise ValueError(f"no parseable judge JSON in: {raw[:200]!r}")


def judge_case(client, question: str, answer: str, chunks: list[dict],
               trace_metadata: dict | None = None) -> dict:
    """Score one case on both rubrics via the gateway. Returns
    {faithfulness, relevancy, faithfulness_rationale, relevancy_rationale}."""
    out: dict = {}
    for rubric in ("faithfulness", "relevancy"):
        completion = client.chat.completions.create(
            model=JUDGE_ALIAS,
            max_tokens=300,
            temperature=0,
            messages=[{"role": "user",
                       "content": build_judge_prompt(rubric, question, answer, chunks)}],
            extra_body={"metadata": {**(trace_metadata or {}),
                                     "generation_name": f"judge-{rubric}"}},
        )
        score, rationale = parse_score(completion.choices[0].message.content or "")
        out[rubric] = score
        out[f"{rubric}_rationale"] = rationale
    return out


def _calibration_obj() -> dict:
    if not CALIBRATION_FILE.exists():
        return {}
    return json.loads(CALIBRATION_FILE.read_text())


def load_calibration() -> dict[str, dict[str, float]]:
    """Owner-ratified labels: {case_id: {faithfulness, relevancy}}."""
    obj = _calibration_obj()
    return obj.get("labels", obj if obj and "constructed" not in obj else {})


def load_anchors() -> list[dict]:
    """Calibration anchors: FROZEN payloads {id, question, answer, chunks[],
    labels} — five director-labeled/owner-ratified real cases plus two
    constructed negatives. Every judged run re-scores exactly these texts,
    so the agreement metric measures judge/rubric movement ALONE. (T7
    finding: judging freshly-generated answers against labels anchored to
    old answers made "drift" apples-to-oranges by design.)"""
    obj = _calibration_obj()
    return obj.get("anchors", obj.get("constructed", []))


def calibration_agreement(records: list[dict]) -> dict | None:
    """Compare judge scores against owner labels for the calibration cases
    present in this run. Owner labels are ground truth (T6 ruling): when they
    disagree, the judge/rubric is what changes."""
    labels = load_calibration()
    if not labels:
        return None
    diffs: list[float] = []
    per_case: dict[str, dict] = {}
    for r in records:
        lab = labels.get(r["id"])
        if not lab or r.get("faithfulness") is None:
            continue
        case_diffs = {}
        for metric in ("faithfulness", "relevancy"):
            d = round(abs(r[metric] - lab[metric]), 4)
            diffs.append(d)
            case_diffs[metric] = {"judge": r[metric], "owner": lab[metric], "abs_diff": d}
        per_case[r["id"]] = case_diffs
    if not diffs:
        return None
    return {
        "labeled_cases_in_run": len(per_case),
        "mean_abs_diff": round(sum(diffs) / len(diffs), 4),
        "within_tolerance_rate": round(
            sum(1 for d in diffs if d <= AGREEMENT_TOLERANCE) / len(diffs), 4),
        "tolerance": AGREEMENT_TOLERANCE,
        "per_case": per_case,
    }
