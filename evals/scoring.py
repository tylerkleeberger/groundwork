"""P1-T5 retrieval + Layer-1 scoring — pure functions, offline-tested (D16 unmarked).

context_precision / context_recall are computed over the RETRIEVED chunk set
(exposed by app.main.AskResponse.retrieved), never over citations. Retrieval
quality is the thing T7 (hybrid + rerank) will move, so it must be measured
independently of what the generator chose to cite — citations are a
generator-selected subset and would systematically under-report recall.

Semantics fixed by the T4 director rulings (see PROGRESS.md / BUILD_JOURNAL):
- R1: answer_must_contain / answer_must_not_contain match CASE-INSENSITIVELY.
- may_cite_any: ANY-ONE-OF acceptance, for both the citation check and recall.
- must_cite_sources: ALL listed sources are required.

No I/O here — the pytest layer (test_evals.py) owns the HTTP call and file
emission. Keeping this module pure is what lets the offline CI floor verify the
measurement math without any running services.
"""
from __future__ import annotations


def relevant_ids(case: dict) -> set[str]:
    """Source ids that count as relevant for a case: the union of the
    hard-required (must_cite_sources) and any-one-of (may_cite_any) sets.
    Empty for not-in-corpus guards, which have no relevant source."""
    return set(case.get("must_cite_sources", [])) | set(case.get("may_cite_any", []))


def context_precision(retrieved: list[str], relevant: set[str]) -> float:
    """Retrieved chunks that are relevant / retrieved.

    Chunk granularity: `retrieved` is one source_id per retrieved chunk and may
    repeat a source, so precision reflects how much of the top-k window was
    spent on relevant material. 0.0 when nothing was retrieved."""
    if not retrieved:
        return 0.0
    hits = sum(1 for sid in retrieved if sid in relevant)
    return round(hits / len(retrieved), 4)


def context_recall(retrieved: list[str], case: dict) -> float:
    """Required sources found / required.

    must_cite_sources → every listed source is required (fraction found).
    may_cite_any      → one is enough (1.0 if any was retrieved, else 0.0).
    Returns 0.0 for cases with no required source; callers should treat
    not-in-corpus guards as N/A rather than scoring them."""
    got = set(retrieved)
    must = list(dict.fromkeys(case.get("must_cite_sources", [])))
    if must:
        found = sum(1 for sid in must if sid in got)
        return round(found / len(must), 4)
    any_of = set(case.get("may_cite_any", []))
    if any_of:
        return 1.0 if got & any_of else 0.0
    return 0.0


def is_answerable(case: dict) -> bool:
    """A case is answerable unless it is an explicit not-in-corpus guard."""
    return case.get("expected_behavior") != "not_found"


def layer1_failures(
    case: dict, answer: str, citations: list[str], confidence: float
) -> list[str]:
    """Deterministic Layer-1 checks. Returns a list of human-readable failure
    strings; an empty list means the case passed. Centralizes the golden-set
    contract so the pytest assertion is a one-liner and the same logic is
    unit-tested offline."""
    fails: list[str] = []

    if not is_answerable(case):
        # Honest-decline expectation. T8 calibrates the real confidence
        # threshold + answer_must_not_contain enforcement; here we accept the
        # v1 signals: a low max-similarity confidence OR the honest-decline
        # phrasing ("I don't know …" / "not found").
        low = answer.lower()
        declined = confidence < 0.5 or "not found" in low or "don't know" in low
        if not declined:
            fails.append(
                f"expected not-found decline but answered with confidence "
                f"{confidence} and no decline phrasing"
            )
        return fails

    for src in case.get("must_cite_sources", []):
        if src not in citations:
            fails.append(f"missing required citation: {src}")

    any_of = case.get("may_cite_any", [])
    if any_of and not (set(citations) & set(any_of)):
        fails.append(f"cited none of may_cite_any {any_of}; got {citations}")

    low = answer.lower()
    for s in case.get("answer_must_contain", []):
        if s.lower() not in low:
            fails.append(f"missing required phrase: {s!r}")
    for s in case.get("answer_must_not_contain", []):
        if s.lower() in low:
            fails.append(f"forbidden phrase present: {s!r}")

    return fails
