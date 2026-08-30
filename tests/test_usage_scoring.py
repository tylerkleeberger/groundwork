"""P6-T1 usage ledger tests (D16 unmarked, offline).

Pinned BEFORE any surface writes to the ledger, in the standing order:
the instrument, then its proof, then the thing it measures.

The property that matters most is negative — that a row CANNOT carry
question or corpus content — because this store's summary gets published
onto an external surface. It is tested here as a refusal, not as a
convention, since P5 spent six tasks establishing that a rule nothing
enforces is not a rule.
"""
import hashlib

import pytest

from evals.usage_scoring import (FIELDS, FLOORS, abandonment_rate,
                                 hash_question, p95_latency_ms, percentile,
                                 record, served_without_queue_rate, summarize)

TS = "2026-08-27T18:00:00Z"


def row(**kw):
    base = dict(ts=TS, surface="slack", kind="ask", question="how do I X?",
                reachable=True, queue_wait_ms=0, route="cheap",
                latency_ms=1200, cost_usd=0.006, outcome="answered")
    base.update(kw)
    return record(**base)


# ---------- the no-content property ----------

def test_question_text_is_hashed_and_never_stored():
    """The store gets SUMMARIZED ONTO AN EXTERNAL SURFACE. The leak scanner
    should have nothing to find here because there is nothing to find, not
    because someone scrubbed it afterwards."""
    secret = "what did my private notes say about the acquisition?"
    r = row(question=secret)
    assert secret not in repr(r)
    assert "acquisition" not in repr(r).lower()
    assert r["question_sha256"] == hashlib.sha256(secret.encode()).hexdigest()
    assert "question" not in r


@pytest.mark.parametrize("field", ["answer", "citations",
                                   "retrieved", "chunks", "source_id",
                                   "brief", "prompt", "text"])
def test_content_bearing_fields_are_REFUSED_not_ignored(field):
    """An allowlist, and a loud one. Silently dropping the field would hide
    a caller's mistake; silently keeping it is the leak."""
    with pytest.raises(ValueError, match="unknown ledger field"):
        record(ts=TS, surface="slack", kind="ask", question_sha256="a" * 64,
               reachable=True, route="cheap", latency_ms=5, cost_usd=0.0,
               outcome="answered", **{field: "some private text"})


def test_the_refusal_says_WHY_for_content_fields():
    with pytest.raises(ValueError, match="published externally"):
        record(ts=TS, surface="slack", kind="ask", question_sha256="a" * 64,
               reachable=True, route="cheap", latency_ms=5, cost_usd=0.0,
               outcome="answered", answer="the private answer")


def test_a_row_carries_exactly_the_allowlisted_fields():
    assert set(row().keys()) == set(FIELDS)


# ---------- contract validation ----------

@pytest.mark.parametrize("kw,msg", [
    (dict(surface="email"), "unknown surface"),
    (dict(kind="summarize"), "unknown kind"),
    (dict(route="gpt"), "unknown route"),
    (dict(outcome="ok"), "unknown outcome"),
    (dict(queue_wait_ms=-1), "cannot be negative"),
    (dict(cost_usd=-0.01), "cannot be negative"),
])
def test_unknown_or_impossible_values_are_refused(kw, msg):
    with pytest.raises(ValueError, match=msg):
        row(**kw)


def test_abandoned_rows_must_not_claim_a_latency():
    """An abandoned request never completed. Storing a latency for it would
    let it be counted as a FAST request in the tail measure — the number
    would improve precisely because someone gave up."""
    with pytest.raises(ValueError, match="EXCLUDED from the latency floor"):
        row(outcome="abandoned", latency_ms=50)
    assert row(outcome="abandoned", latency_ms=None)["latency_ms"] is None


def test_completed_rows_must_carry_a_latency():
    with pytest.raises(ValueError, match="needs latency_ms"):
        row(outcome="answered", latency_ms=None)


def test_question_and_hash_are_mutually_exclusive():
    with pytest.raises(ValueError, match="not both"):
        record(ts=TS, surface="code", kind="ask", question="x",
               question_sha256="b" * 64, reachable=True, route="cheap",
               latency_ms=1, cost_usd=0.0, outcome="answered")


# ---------- the floors ----------

def test_percentile_is_nearest_rank_and_returns_a_real_observation():
    """Interpolation invents a latency nobody experienced."""
    vals = [10.0, 20.0, 30.0, 40.0, 100.0]
    assert percentile(vals, 0.95) in vals
    assert percentile(vals, 0.95) == 100.0
    assert percentile([], 0.95) is None
    assert percentile([7.0], 0.5) == 7.0


def test_a_decline_counts_as_SERVED_not_as_a_failure():
    """The floor must not push the product toward answering everything —
    that is the exact failure the not-found gate exists to prevent."""
    rows = [row(outcome="answered"),
            row(outcome="declined", route="none", cost_usd=0.0, latency_ms=300)]
    assert served_without_queue_rate(rows) == 1.0


def test_queued_and_abandoned_requests_count_against_the_reachability_floor():
    rows = [row(),                                        # served
            row(queue_wait_ms=90_000, reachable=False),   # queued
            row(outcome="abandoned", latency_ms=None)]    # left
    assert served_without_queue_rate(rows) == round(1 / 3, 4)


def test_p95_excludes_abandoned_rather_than_counting_them_as_zero():
    """Counting a give-up as a 0ms request would make the tail improve as
    the product got less usable."""
    completed = [row(latency_ms=v) for v in (100, 200, 300, 400, 5000)]
    assert p95_latency_ms(completed) == 5000
    with_quit = completed + [row(outcome="abandoned", latency_ms=None)]
    assert p95_latency_ms(with_quit) == 5000, "an abandon must not move the tail"


def test_abandonment_rate_counts_what_p95_excludes():
    rows = [row(), row(), row(outcome="abandoned", latency_ms=None)]
    assert abandonment_rate(rows) == round(1 / 3, 4)


def test_floors_are_defined_without_thresholds_until_there_is_a_distribution():
    """A threshold belongs to its input distribution. Guessing one here
    would invent the number this instrument exists to measure."""
    for name, spec in FLOORS.items():
        assert spec["threshold"] is None, f"{name} has a guessed target"
        assert spec["direction"] in ("floor", "ceiling")
        assert spec["why"], f"{name} must say why it is a floor"


def test_empty_ledger_yields_None_not_a_flattering_zero():
    """No data is not a perfect score. The same refusal the leak scanner
    makes on an empty seed set: a verdict nothing earned."""
    assert served_without_queue_rate([]) is None
    assert p95_latency_ms([]) is None
    assert abandonment_rate([]) is None


# ---------- the summary ----------

def test_summary_is_a_clean_function_of_the_rows():
    rows = [
        row(surface="slack", kind="ask"),
        row(surface="cowork", kind="research", route="frontier",
            latency_ms=42_000, cost_usd=0.095),
        row(surface="code", kind="related", route="none", cost_usd=0.0,
            outcome="declined", latency_ms=250),
        row(surface="operator", queue_wait_ms=120_000, reachable=False),
        row(outcome="abandoned", latency_ms=None),
    ]
    s = summarize(rows)
    assert s["requests"] == 5
    assert s["by_surface"] == {"code": 1, "cowork": 1, "operator": 1, "slack": 2}
    assert s["by_outcome"] == {"abandoned": 1, "answered": 3, "declined": 1}
    assert s["queued"] == 1 and s["p95_queue_wait_ms"] == 120_000
    assert s["cost_usd_total"] == round(0.006 * 3 + 0.095, 6)
    assert set(s["floors"]) == set(FLOORS)
    assert s["thresholds"] == {k: None for k in FLOORS}


def test_summary_carries_no_hashes_and_no_content():
    """What gets published must not carry even the hashes — a count of
    distinct questions is the useful part, and the digests are not."""
    secret = "a question about something private"
    s = summarize([row(question=secret)])
    blob = repr(s)
    assert hash_question(secret) not in blob
    assert secret not in blob
    assert s["distinct_questions"] == 1


def test_distinct_questions_counts_repeats_once():
    rows = [row(question="same"), row(question="same"), row(question="other")]
    assert summarize(rows)["distinct_questions"] == 2


def test_summary_of_an_empty_ledger_is_honest():
    s = summarize([])
    assert s["requests"] == 0
    assert all(v is None for v in s["floors"].values())
