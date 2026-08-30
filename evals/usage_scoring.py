"""P6-T1 usage ledger — pure scoring logic (D16 unmarked, offline).

Built BEFORE the surfaces that will write to it, in the same order every
phase has used: the measuring instrument precedes the thing measured. No
I/O here — this module owns the record contract, the floors, and the
summary. Persistence and the publishing path are deliberately NOT here
(SPEC-P6 is in review and may amend both).

WHY THIS EXISTS. P2's usage window closed early and left "is it useful?"
unmeasured — the phase closed on evidence rather than on criteria, and
recorded that honestly, but the number was simply never taken. P6's gate
should not be a feeling. This is the instrument that makes it a number.

WHAT A ROW IS. One row per invocation, from any surface:

    { ts                : ISO-8601 UTC, when the request ARRIVED
      surface           : slack | cowork | code | operator
      kind              : ask | related | research
      question_sha256   : hex digest — NEVER the text (see below)
      reachable         : bool — was the engine reachable at arrival?
      queue_wait_ms     : int >= 0 — 0 when served directly
      route             : cheap | frontier | local | none  (none = declined
                          at the gate, zero generation tokens)
      latency_ms        : int >= 0, or None when abandoned
      cost_usd          : float >= 0
      outcome           : answered | declined | abandoned }

NO PERSONAL CONTENT, ENFORCED AT CONSTRUCTION. Question text is hashed
and never stored; there is no field for an answer, a citation, a source
id, or a chunk. This store gets SUMMARIZED ONTO AN EXTERNAL SURFACE, so
it is built as something the leak scanner can find nothing in — rather
than as something we scrub later. `record()` is the only way to build a
row and it REFUSES unknown fields, which is what makes the property a
structural one instead of a convention. P5 spent six tasks learning the
difference.

FLOORS, NOT AVERAGES (the standing rule since P1-T7). A mean latency and
a mean success rate would both look fine on a system that is unreachable
a third of the time and slow in the tail. The floors are defined in
`FLOORS` below with the reasoning attached to each.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable

SURFACES = ("slack", "cowork", "code", "operator")
KINDS = ("ask", "related", "research")
ROUTES = ("cheap", "frontier", "local", "none")
OUTCOMES = ("answered", "declined", "abandoned")

# Every field a row may carry. An allowlist, not a denylist: a denylist
# fails open the first time someone adds a field nobody thought about,
# and the field nobody thought about is exactly how content gets in.
FIELDS = ("ts", "surface", "kind", "question_sha256", "reachable",
          "queue_wait_ms", "route", "latency_ms", "cost_usd", "outcome")

# Fields that would carry corpus or question content if they ever existed.
# Named explicitly so the refusal message can say WHY rather than just no.
FORBIDDEN = ("text", "answer", "citations", "retrieved",
             "chunks", "source_id", "sources", "brief", "prompt")


def hash_question(question: str) -> str:
    """The only thing about a question that reaches the ledger.

    A hash lets us count DISTINCT questions and spot repeats — which is
    most of what a usage measure needs — while making the row useless to
    anyone who obtains it. Unsalted on purpose: the point is not to defeat
    a dictionary attack on a question someone already suspects, it is that
    the ledger never holds the text at all.
    """
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def record(*, ts: str, surface: str, kind: str, question: str | None = None,
           question_sha256: str | None = None, reachable: bool,
           queue_wait_ms: int = 0, route: str, latency_ms: int | None,
           cost_usd: float, outcome: str, **extra: Any) -> dict:
    """Build one validated ledger row. THE ONLY WAY TO MAKE ONE.

    Accepts `question` as a convenience and hashes it immediately — the
    raw text never enters the returned dict. Passing any other unexpected
    keyword is refused rather than ignored: a row that silently drops a
    field a caller thought it was storing is worse than an error, and a
    row that silently KEEPS one is the leak this design exists to prevent.
    """
    if extra:
        bad = sorted(extra)
        why = ("; that field would put question or corpus content in a store "
               "whose summary is published externally"
               if any(k in FORBIDDEN for k in bad) else "")
        raise ValueError(f"unknown ledger field(s): {bad}{why}. "
                         f"Allowed: {list(FIELDS)}")
    if question is not None and question_sha256 is not None:
        raise ValueError("pass question OR question_sha256, not both")
    if question is not None:
        question_sha256 = hash_question(question)
    if not question_sha256:
        raise ValueError("a row needs question_sha256 (or question to hash)")

    if surface not in SURFACES:
        raise ValueError(f"unknown surface {surface!r}; expected {list(SURFACES)}")
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected {list(KINDS)}")
    if route not in ROUTES:
        raise ValueError(f"unknown route {route!r}; expected {list(ROUTES)}")
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; expected {list(OUTCOMES)}")
    if queue_wait_ms < 0 or cost_usd < 0:
        raise ValueError("queue_wait_ms and cost_usd cannot be negative")
    if latency_ms is not None and latency_ms < 0:
        raise ValueError("latency_ms cannot be negative")
    if outcome == "abandoned" and latency_ms is not None:
        raise ValueError("an abandoned request has no completion latency; "
                         "pass latency_ms=None so it is EXCLUDED from the "
                         "latency floor rather than counted as fast")
    if outcome != "abandoned" and latency_ms is None:
        raise ValueError(f"outcome {outcome!r} completed and needs latency_ms")

    return {"ts": ts, "surface": surface, "kind": kind,
            "question_sha256": question_sha256, "reachable": bool(reachable),
            "queue_wait_ms": int(queue_wait_ms), "route": route,
            "latency_ms": latency_ms, "cost_usd": float(cost_usd),
            "outcome": outcome}


# ---------- floors ----------

def percentile(values: list[float], p: float) -> float | None:
    """NEAREST-RANK percentile, deliberately not interpolated.

    Interpolating invents a latency nobody experienced. Nearest-rank always
    returns a number some real request actually took, which is the only
    kind of number worth putting in front of a reader who might act on it.
    """
    if not values:
        return None
    ordered = sorted(values)
    # ceil(p * n), 1-indexed. Written with math.ceil rather than an integer
    # trick: the first version truncated before rounding up, so the p95 of
    # five requests returned the FOURTH-slowest and the tail it exists to
    # expose disappeared. A percentile that quietly under-reports is worse
    # than no percentile.
    rank = max(1, min(len(ordered), math.ceil(p * len(ordered))))
    return ordered[rank - 1]


def served_without_queue_rate(rows: Iterable[dict]) -> float | None:
    """FLOOR 1 — the share of requests the engine answered on the spot.

    D19 bets on REACHABILITY over relocation: the engine stays local and a
    tunnel reaches it, with the queue as the fallback for when the laptop
    is not there. This number is that bet, scored. If most requests queue,
    the bet failed regardless of how good the eventual answers were.

    A DECLINE COUNTS AS SERVED. The system responding "I don't know" is a
    success of the thing P2 built on purpose, and a floor that punished it
    would push the product toward answering everything — the exact failure
    the not-found gate exists to prevent. Abandoned requests count against
    this floor: the user left, and why is not the floor's business.
    """
    rows = list(rows)
    if not rows:
        return None
    served = [r for r in rows
              if r["outcome"] in ("answered", "declined") and r["queue_wait_ms"] == 0]
    return round(len(served) / len(rows), 4)


def p95_latency_ms(rows: Iterable[dict]) -> int | None:
    """FLOOR 2 — the tail, because the tail is what people quit over.

    A mean hides the requests that made someone give up and go read the
    file themselves. Abandoned rows carry no latency and are EXCLUDED here
    rather than counted as zero — they are counted in `abandonment_rate`,
    where they mean something.
    """
    lat = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    v = percentile([float(x) for x in lat], 0.95)
    return None if v is None else int(v)


def abandonment_rate(rows: Iterable[dict]) -> float | None:
    """FLOOR 3 — the share of requests nobody waited for.

    The most honest usefulness signal available without asking anyone: a
    request that was started and left is a request whose answer was not
    worth its wait. Reported as a ceiling to stay under.
    """
    rows = list(rows)
    if not rows:
        return None
    return round(sum(1 for r in rows if r["outcome"] == "abandoned") / len(rows), 4)


# The floors themselves. Thresholds are DELIBERATELY ABSENT until there is
# a distribution to derive them from — the standing rule is that a
# threshold belongs to its input distribution, and P5-T3 re-proved it the
# hard way when the same pipeline's margin moved 8x across two corpora.
# Guessing a target here would be inventing the number this instrument
# exists to measure.
FLOORS = {
    "served_without_queue_rate": {
        "fn": served_without_queue_rate, "direction": "floor",
        "why": "D19's reachability bet, scored. Declines count as served.",
        "threshold": None, "derive_after": "the first usage window closes",
    },
    "p95_latency_ms": {
        "fn": p95_latency_ms, "direction": "ceiling",
        "why": "the tail is what people quit over; a mean hides it.",
        "threshold": None, "derive_after": "the first usage window closes",
    },
    "abandonment_rate": {
        "fn": abandonment_rate, "direction": "ceiling",
        "why": "a request left unwaited-for is an answer that was not worth its wait.",
        "threshold": None, "derive_after": "the first usage window closes",
    },
}


# ---------- summary ----------

def summarize(rows: Iterable[dict]) -> dict:
    """The ledger's published shape — a CLEAN FUNCTION of the rows.

    Deliberately a pure transformation with no I/O and no formatting: the
    publishing path (SPEC-P6, a later task) consumes this, and keeping the
    two apart means the surface can change without touching the
    measurement. Contains counts and floors only — no hashes, and by
    construction nothing that could carry content.
    """
    rows = list(rows)
    by = lambda key: {  # noqa: E731 — small, local, and clearer inline
        v: sum(1 for r in rows if r[key] == v)
        for v in sorted({r[key] for r in rows})
    }
    queued = [r for r in rows if r["queue_wait_ms"] > 0]
    return {
        "requests": len(rows),
        "distinct_questions": len({r["question_sha256"] for r in rows}),
        "by_surface": by("surface"),
        "by_kind": by("kind"),
        "by_route": by("route"),
        "by_outcome": by("outcome"),
        "queued": len(queued),
        "p95_queue_wait_ms": (
            None if not queued
            else int(percentile([float(r["queue_wait_ms"]) for r in queued], 0.95))),
        "cost_usd_total": round(sum(r["cost_usd"] for r in rows), 6),
        "floors": {name: spec["fn"](rows) for name, spec in FLOORS.items()},
        # Stated in the artifact itself, so a reader of the published
        # summary cannot mistake an unset target for a met one.
        "thresholds": {name: spec["threshold"] for name, spec in FLOORS.items()},
    }
