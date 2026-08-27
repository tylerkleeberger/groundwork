"""P3-T3 offline tests (D16 unmarked) — durable run state.

The centerpiece is the KILL/RESUME PROPERTY (SPEC-P3 §B / BLUEPRINT P3
acceptance, fake-stage form): a run that dies at step k resumes without
re-executing steps 1..k-1 — paid-for work is never re-bought. The fake
store implements the PostgresStore interface over dicts; the SQL store's
roundtrip is covered by the live-marked test at the bottom.
"""
import pytest

from app.research_state import next_stage, pending_steps, run_research

PLAN = {"sub_questions": [
    {"id": "sq-1", "question": "q one"},
    {"id": "sq-2", "question": "q two"},
    {"id": "sq-3", "question": "q three"},
]}


class FakeStore:
    """Dict-backed stand-in honoring the PostgresStore interface and its
    checkpoint semantics (each save_* is atomic; load returns the T1
    run-record shape)."""

    def __init__(self, question="research q"):
        self.run = {"run_id": "r1", "question": question, "plan": None,
                    "status": "planning", "brief": None,
                    "declared_gaps": [], "steps": []}
        self.locked = False

    def try_lock(self, run_id):
        if self.locked:
            return False
        self.locked = True
        return True

    def unlock(self, run_id):
        self.locked = False

    def load_run(self, run_id):
        import copy
        return copy.deepcopy(self.run)

    def save_plan(self, run_id, plan):
        self.run["plan"] = plan
        self.run["status"] = "running"
        if not self.run["steps"]:
            self.run["steps"] = [
                {"step_no": i, "sub_question_id": s["id"],
                 "sub_question": s["question"], "status": "pending",
                 "result": None, "error": None}
                for i, s in enumerate(plan["sub_questions"], start=1)]

    def save_step(self, run_id, step_no, result):
        step = self.run["steps"][step_no - 1]
        step.update(status="done", result=result, error=None)

    def mark_step_failed(self, run_id, step_no, error):
        self.run["steps"][step_no - 1].update(status="failed", error=error)

    def save_brief(self, run_id, brief, declared_gaps):
        self.run.update(brief=brief, declared_gaps=declared_gaps,
                        status="done")

    def set_status(self, run_id, status):
        self.run["status"] = status


def counting_worker(record: list, die_on: str | None = None):
    def worker(sub_question: str) -> dict:
        if sub_question == die_on:
            raise RuntimeError("simulated mid-run death")
        record.append(sub_question)
        return {"answer": f"answer to {sub_question}", "citations": ["c1"],
                "retrieved": ["c1"], "gate_score": 1.0,
                "routed_to": "cheap", "route_reason": "default",
                "declined": False}
    return worker


def synth(run):
    return ("brief over " + str(len(run["steps"])) + " steps", [])


# ---------- pure resume logic ----------

def test_next_stage_walks_the_lifecycle():
    run = {"plan": None, "steps": [], "brief": None}
    assert next_stage(run) == "plan"
    run = {"plan": PLAN, "steps": [{"step_no": 1, "status": "pending"}],
           "brief": None}
    assert next_stage(run) == "workers"
    run["steps"][0]["status"] = "done"
    assert next_stage(run) == "synthesize"
    run["brief"] = "b"
    assert next_stage(run) == "done"


def test_pending_treats_failed_and_pending_alike():
    run = {"steps": [{"step_no": 1, "status": "done"},
                     {"step_no": 2, "status": "failed"},
                     {"step_no": 3, "status": "pending"}]}
    assert pending_steps(run) == [2, 3]


# ---------- the driver ----------

def test_fresh_run_executes_everything():
    store, calls = FakeStore(), []
    run = run_research(store, "r1", lambda q: PLAN,
                       counting_worker(calls), synth)
    assert run["status"] == "done" and run["brief"]
    assert sorted(calls) == ["q one", "q three", "q two"]  # parallel: any order
    assert not store.locked  # lock released


def test_worker_death_then_resume_never_rebuys_done_steps():
    """T4 parallel semantics: when q-two dies, the OTHER workers finish
    and checkpoint before the error surfaces (maximally resumable), the
    dead step is marked failed, synthesis never runs — and resume
    re-buys ONLY the dead step."""
    store, calls = FakeStore(), []
    with pytest.raises(RuntimeError, match="simulated"):
        run_research(store, "r1", lambda q: PLAN,
                     counting_worker(calls, die_on="q two"), synth)
    assert sorted(calls) == ["q one", "q three"]  # siblings completed
    snapshot = store.load_run("r1")
    assert [s["status"] for s in snapshot["steps"]] == ["done", "failed", "done"]
    assert snapshot["brief"] is None  # synthesis never ran on a failed run
    assert not store.locked  # lock released even on death

    resumed_calls: list = []
    plan_calls: list = []

    def plan_fn(q):
        plan_calls.append(q)
        return PLAN

    run = run_research(store, "r1", plan_fn,
                       counting_worker(resumed_calls), synth)
    assert plan_calls == []             # plan never re-ran
    assert resumed_calls == ["q two"]   # done work never re-bought
    assert run["status"] == "done" and run["brief"]


def test_hard_kill_shape_resumes_identically():
    """A kill -9 leaves no 'failed' mark — steps just sit 'pending'.
    Resume must treat that snapshot exactly like the marked one."""
    store, calls = FakeStore(), []
    store.save_plan("r1", PLAN)
    store.save_step("r1", 1, {"answer": "a", "citations": [], "retrieved": [],
                              "declined": True})
    run = run_research(store, "r1",
                       lambda q: (_ for _ in ()).throw(AssertionError("no replan")),
                       counting_worker(calls), synth)
    assert sorted(calls) == ["q three", "q two"]
    assert run["status"] == "done"


def test_synthesis_only_resume():
    """All steps done, brief lost/never written → resume runs synthesis
    alone: zero worker calls, zero plan calls."""
    store, calls = FakeStore(), []
    store.save_plan("r1", PLAN)
    for i in (1, 2, 3):
        store.save_step("r1", i, {"answer": "a", "citations": ["c1"],
                                  "retrieved": ["c1"], "declined": False})
    run = run_research(store, "r1", lambda q: PLAN,
                       counting_worker(calls), synth)
    assert calls == []
    assert run["status"] == "done" and run["brief"]


def test_concurrent_resume_refused_by_lock():
    store = FakeStore()
    store.locked = True  # someone else is executing this run
    with pytest.raises(RuntimeError, match="advisory lock"):
        run_research(store, "r1", lambda q: PLAN,
                     counting_worker([]), synth)


def test_completed_run_is_a_noop():
    store, calls = FakeStore(), []
    run_research(store, "r1", lambda q: PLAN, counting_worker(calls), synth)
    again: list = []
    run = run_research(store, "r1", lambda q: PLAN,
                       counting_worker(again), synth)
    assert again == [] and run["status"] == "done"


# ---------- live roundtrip (services required) ----------

@pytest.mark.live
def test_postgres_store_roundtrip_and_lock():
    import os

    import psycopg

    from app.research_state import PostgresStore
    with psycopg.connect(os.environ["APP_DATABASE_URL"],
                         autocommit=True) as conn:
        store = PostgresStore(conn)
        store.ensure_schema()
        run_id = store.create_run("live roundtrip q")
        store.save_plan(run_id, PLAN)
        store.save_step(run_id, 1, {"answer": "a", "citations": ["c1"],
                                    "retrieved": ["c1"], "declined": False})
        run = store.load_run(run_id)
        assert run["question"] == "live roundtrip q"
        assert [s["status"] for s in run["steps"]] == ["done", "pending", "pending"]
        assert store.try_lock(run_id)
        with psycopg.connect(os.environ["APP_DATABASE_URL"],
                             autocommit=True) as conn2:
            assert not PostgresStore(conn2).try_lock(run_id)
        store.unlock(run_id)
        # leave no fixture rows behind
        conn.execute("DELETE FROM research_steps WHERE run_id=%s", (run_id,))
        conn.execute("DELETE FROM research_runs WHERE id=%s", (run_id,))


def test_postgres_store_refuses_transactional_connection():
    """T4 durability-drill regression pin: on a non-autocommit
    connection, checkpoints become savepoints and never commit — the
    store must refuse construction rather than be silently nondurable."""
    class FakeConn:
        autocommit = False
    with pytest.raises(ValueError, match="autocommit"):
        __import__("app.research_state", fromlist=["PostgresStore"]) \
            .PostgresStore(FakeConn())
