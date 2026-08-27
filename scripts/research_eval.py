"""P3-T4 research-case runner: execute the certified research set
end-to-end (planner → parallel workers → synthesizer → $0 critic) and
score every run with the FULL harness — score_run over trajectories,
never brief_only (T4 definition of done).

Usage (from repo root, .env loaded):
  .venv/bin/python scripts/research_eval.py [--runs case_id=run_id ...]

--runs maps a case to an ALREADY-EXECUTED run id (e.g. the kill/resume
demonstration run) so paid-for work is scored, not re-bought. All other
cases execute fresh. Output: evals/results/research-<ts>.json with
per-case rows, trajectory detail, critic reports, and per-role costs
(planner/synthesizer from the research trace, workers from their ask
traces — joined on the trace ids the run record carries).
"""
import datetime
import json
import os
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.research import critic_report, execute_research  # noqa: E402
from app.research_state import PostgresStore  # noqa: E402
from evals.research_scoring import score_run, summarize  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
CASES = REPO / "evals" / "research_set.jsonl"
RESULTS_DIR = REPO / "evals" / "results"


def langfuse_trace_cost(trace_id: str | None) -> float | None:
    """Sum a trace's observation costs via the Langfuse public API."""
    if not trace_id:
        return None
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:8300")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    try:
        r = requests.get(f"{host}/api/public/traces/{trace_id}",
                         auth=auth, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("totalCost") is not None:
            return float(data["totalCost"])
        return sum(float(o.get("calculatedTotalCost") or 0)
                   for o in data.get("observations", []))
    except Exception as exc:  # cost lookup must never fail the eval
        print(f"  cost lookup failed for {trace_id}: {exc}")
        return None


def role_costs(run: dict, store: PostgresStore) -> dict:
    """§D per-role breakdown: research trace = planner + synthesizer;
    each worker's cost rides its own ask trace."""
    row = store.conn.execute(
        "SELECT trace_id FROM research_runs WHERE id=%s",
        (run["run_id"],)).fetchone()
    research_cost = langfuse_trace_cost(row[0] if row else None)
    workers = []
    for s in run["steps"]:
        tid = (s.get("result") or {}).get("worker_trace_id")
        workers.append({"sub_question_id": s["sub_question_id"],
                        "routed_to": (s.get("result") or {}).get("routed_to"),
                        "cost": langfuse_trace_cost(tid)})
    worker_total = sum(w["cost"] or 0 for w in workers)
    total = (research_cost or 0) + worker_total
    return {"planner_plus_synth": research_cost,
            "workers": workers,
            "worker_total": round(worker_total, 6),
            "run_total": round(total, 6)}


def main() -> int:
    import psycopg
    premapped: dict[str, str] = {}
    args = sys.argv[1:]
    if args and args[0] == "--runs":
        for pair in args[1:]:
            case_id, run_id = pair.split("=", 1)
            premapped[case_id] = run_id

    cases = [json.loads(l) for l in CASES.read_text().splitlines() if l.strip()]
    rows, costs = [], []
    with psycopg.connect(os.environ["APP_DATABASE_URL"],
                         autocommit=True) as conn:
        store = PostgresStore(conn)
        for case in cases:
            cid = case["id"]
            if cid in premapped:
                run = store.load_run(premapped[cid])
                run["critic"] = critic_report(run)
                print(f"{cid}: scoring pre-executed run {premapped[cid][:8]}…")
            else:
                print(f"{cid}: executing…")
                run = execute_research(case["question"])
            row = score_run(case, run)
            row["run_id"] = run["run_id"]
            row["critic"] = run.get("critic")
            row["routes"] = [
                (s.get("result") or {}).get("routed_to")
                for s in run["steps"]]
            cost = role_costs(run, store)
            row["cost"] = cost
            costs.append(cost["run_total"])
            rows.append(row)
            print(f"  passed={row['passed']} (brief_only="
                  f"{row['passed_brief_only']}) · steps={len(run['steps'])}"
                  f" · cost=${cost['run_total']}")

    out = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "kind": "research",
        "summary": {**summarize(rows),
                    "mean_cost_per_question": round(sum(costs) / len(costs), 6)
                    if costs else None,
                    "max_cost": max(costs) if costs else None},
        "cases": rows,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    path = RESULTS_DIR / f"research-{ts}.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nsummary: {json.dumps(out['summary'])}")
    print(f"results → {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
