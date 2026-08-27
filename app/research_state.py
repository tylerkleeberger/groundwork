"""P3-T3 durable run state — the smallest durable thing (SPEC-P3 §B).

Two tables in the app Postgres (beside `chunks`), transactional
checkpoint writes at model-call boundaries, and a RESUMABLE driver:
calling run_research() on a fresh run executes everything; calling it on
a partial run (process died at step 4 of 6) executes only what is
missing. Idempotency is by construction — workers only read the corpus
and call the gateway, and a re-run overwrites its own step row keyed
(run_id, step_no).

Layer split (D16): the resume DECISIONS (pending_steps, next_stage) and
the driver are pure over a store interface — offline-tested with a fake
store in tests/test_research_state.py, including the kill/resume
property. PostgresStore owns the SQL; its roundtrip is live-marked.

load_run() returns exactly the T1 run-record contract
(evals/research_scoring.py docstring): what the state layer persists IS
what the harness scores — one shape, no translation layer to drift.

Deliberately NOT built (§B): no queue, no scheduler, no worker
processes, no leases, no auto-resume on start. Concurrent resume of one
run is refused via a Postgres advisory lock — one guard, not a protocol.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Callable

import psycopg

DDL = """
CREATE TABLE IF NOT EXISTS research_runs (
    id          uuid PRIMARY KEY,
    question    text NOT NULL,
    plan        jsonb,
    status      text NOT NULL DEFAULT 'planning',
    brief       text,
    declared_gaps jsonb,
    trace_id    text,
    cost_usd    numeric,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS research_steps (
    run_id      uuid NOT NULL REFERENCES research_runs(id),
    step_no     int  NOT NULL,
    sub_question_id text NOT NULL,
    sub_question    text NOT NULL,
    status      text NOT NULL DEFAULT 'pending',
    result      jsonb,
    error       text,
    completed_at timestamptz,
    PRIMARY KEY (run_id, step_no)
);
"""


# ---------- pure resume logic (offline, D16 unmarked) ----------

def pending_steps(run: dict) -> list[int]:
    """Step numbers still owed work — anything not 'done' re-runs
    (a 'failed' mark and a kill-orphaned 'pending' resume identically)."""
    return [s["step_no"] for s in run.get("steps", [])
            if s.get("status") != "done"]


def next_stage(run: dict) -> str:
    """Where a (possibly partial) run resumes: plan → workers →
    synthesize → done. Derived from persisted state alone — the driver
    holds nothing in memory a crash could lose."""
    if not run.get("plan"):
        return "plan"
    if pending_steps(run):
        return "workers"
    if run.get("brief") is None:
        return "synthesize"
    return "done"


# ---------- store (SQL lives here; live-marked test coverage) ----------

class PostgresStore:
    """Thin checkpoint store over the app Postgres. Each save_* is one
    transaction — the §B write points, nothing finer.

    REQUIRES an autocommit connection, enforced loudly: on a default
    (transactional) connection, `conn.transaction()` blocks nest inside
    the caller's implicit outer transaction as SAVEPOINTS and nothing
    commits until that outer transaction ends — checkpoints that feel
    durable and aren't. Found live by the T4 kill/resume drill: step
    counts jumped 0/0 → 5/5 with no intermediate states because no
    checkpoint had committed; a real kill would have lost the entire
    run. A silently-nondurable store is the failure class this table
    exists to prevent, so the store refuses to be constructed wrong."""

    def __init__(self, conn: psycopg.Connection):
        if not conn.autocommit:
            raise ValueError(
                "PostgresStore requires an autocommit connection "
                "(psycopg.connect(..., autocommit=True)) — on a "
                "transactional connection the per-checkpoint "
                "transactions become savepoints and never commit")
        self.conn = conn

    def ensure_schema(self) -> None:
        with self.conn.transaction():
            self.conn.execute(DDL)

    def create_run(self, question: str) -> str:
        run_id = str(uuid.uuid4())
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO research_runs (id, question) VALUES (%s, %s)",
                (run_id, question))
        return run_id

    def try_lock(self, run_id: str) -> bool:
        """Session-scoped advisory lock keyed on the run id — concurrent
        resume of the same run is refused, not queued."""
        row = self.conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
            (run_id,)).fetchone()
        return bool(row[0])

    def unlock(self, run_id: str) -> None:
        self.conn.execute(
            "SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (run_id,))

    def save_plan(self, run_id: str, plan: dict) -> None:
        """Checkpoint 1: plan lands and step rows are born 'pending' in
        the same transaction — a crash between them cannot orphan."""
        with self.conn.transaction():
            self.conn.execute(
                "UPDATE research_runs SET plan=%s, status='running',"
                " updated_at=now() WHERE id=%s",
                (json.dumps(plan), run_id))
            for i, sub in enumerate(plan.get("sub_questions", []), start=1):
                self.conn.execute(
                    """INSERT INTO research_steps
                       (run_id, step_no, sub_question_id, sub_question)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (run_id, step_no) DO NOTHING""",
                    (run_id, i, sub["id"], sub["question"]))

    def save_step(self, run_id: str, step_no: int, result: dict) -> None:
        """Checkpoint 2 (per worker): the resume unit is one model call."""
        with self.conn.transaction():
            self.conn.execute(
                """UPDATE research_steps SET status='done', result=%s,
                   error=NULL, completed_at=now()
                   WHERE run_id=%s AND step_no=%s""",
                (json.dumps(result), run_id, step_no))

    def mark_step_failed(self, run_id: str, step_no: int, error: str) -> None:
        with self.conn.transaction():
            self.conn.execute(
                """UPDATE research_steps SET status='failed', error=%s
                   WHERE run_id=%s AND step_no=%s""",
                (error[:500], run_id, step_no))

    def save_brief(self, run_id: str, brief: str,
                   declared_gaps: list) -> None:
        """Checkpoint 3: synthesis lands, run completes."""
        with self.conn.transaction():
            self.conn.execute(
                """UPDATE research_runs SET brief=%s, declared_gaps=%s,
                   status='done', updated_at=now() WHERE id=%s""",
                (brief, json.dumps(declared_gaps), run_id))

    def set_status(self, run_id: str, status: str) -> None:
        with self.conn.transaction():
            self.conn.execute(
                "UPDATE research_runs SET status=%s, updated_at=now()"
                " WHERE id=%s", (status, run_id))

    def load_run(self, run_id: str) -> dict:
        """The T1 run-record contract, straight from the tables."""
        row = self.conn.execute(
            """SELECT question, plan, status, brief, declared_gaps
               FROM research_runs WHERE id=%s""", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"no research run {run_id}")
        steps = self.conn.execute(
            """SELECT step_no, sub_question_id, sub_question, status,
                      result, error
               FROM research_steps WHERE run_id=%s ORDER BY step_no""",
            (run_id,)).fetchall()
        return {
            "run_id": run_id,
            "question": row[0],
            "plan": row[1],
            "status": row[2],
            "brief": row[3],
            "declared_gaps": row[4] or [],
            "steps": [{"step_no": s[0], "sub_question_id": s[1],
                       "sub_question": s[2], "status": s[3],
                       "result": s[4], "error": s[5]} for s in steps],
        }


# ---------- resumable driver (offline-tested with a fake store) ----------

def run_research(store: Any, run_id: str,
                 plan_fn: Callable[[str], dict],
                 worker_fn: Callable[[str], dict],
                 synth_fn: Callable[[dict], tuple[str, list]]) -> dict:
    """Execute (or RESUME) a research run to completion. Every stage
    consults persisted state first — the driver is stateless between
    calls, so a kill at any point costs only the in-flight step.

    plan_fn(question) -> plan dict ({sub_questions: [{id, question, ...}]})
    worker_fn(sub_question) -> step result dict (the T1 contract's
        result shape; T4 wires this to run_ask)
    synth_fn(run_record) -> (brief, declared_gaps)

    Workers run CONCURRENTLY (SPEC-P3 §A asyncio fan-out, added in T4):
    each pending step executes in its own thread via asyncio.to_thread —
    worker_fn is synchronous and self-contained — while ALL store writes
    stay on the coordinating thread (one psycopg connection is not
    thread-safe). Steps checkpoint IN COMPLETION ORDER, so a kill mid
    fan-out loses only in-flight steps, never completed ones. A worker
    exception is checkpointed as that step's 'failed' mark; the other
    workers finish and checkpoint before the error re-raises — the run
    stays maximally resumable; synthesis never executes on a failed run.
    """
    import asyncio

    if not store.try_lock(run_id):
        raise RuntimeError(f"research run {run_id} is already being "
                           "executed elsewhere (advisory lock held)")
    try:
        run = store.load_run(run_id)
        if next_stage(run) == "plan":
            store.save_plan(run_id, plan_fn(run["question"]))
            run = store.load_run(run_id)
        pending = [s for s in run["steps"] if s["status"] != "done"]
        if pending:
            async def _fan_out():
                async def one(step):
                    try:
                        result = await asyncio.to_thread(
                            worker_fn, step["sub_question"])
                        return step, result, None
                    except Exception as exc:  # captured, raised after saves
                        return step, None, exc
                errors = []
                for task in asyncio.as_completed(
                        [one(s) for s in pending]):
                    step, result, exc = await task
                    if exc is None:
                        store.save_step(run_id, step["step_no"], result)
                    else:
                        store.mark_step_failed(run_id, step["step_no"],
                                               repr(exc))
                        errors.append(exc)
                if errors:
                    raise errors[0]
            asyncio.run(_fan_out())
        run = store.load_run(run_id)
        if next_stage(run) == "synthesize":
            brief, gaps = synth_fn(run)
            store.save_brief(run_id, brief, gaps)
        return store.load_run(run_id)
    finally:
        store.unlock(run_id)
