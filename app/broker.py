"""P4-T1 action broker — deterministic code, no model in the loop
(SPEC-P4 §A, ratified 2026-07-18).

The manual governance pattern, mechanized: permission check (config,
unknown = denied) → MANDATORY human approval for every v1 write (no
auto-approve tier — earned later, like everything; "the gate pattern is
uniform or it is nothing") → execute → append-only action log with full
request/response + provenance.

Layer split (D16): policy_decision and render_approval_payload are pure
functions, pinned by the action golden set (evals/action_set.jsonl,
offline). ActionStore owns the SQL (autocommit-guarded — the P3
savepoint lesson applied at birth); dispatch() orchestrates. T1 ships
ZERO tool executors by design — the registry is empty until T2; the
dry-run contract and a test registry exercise every path first.

D12 at the arg boundary: everything reaching a tool arg from
retrieved/generated content is DATA with provenance; the approval
payload renders args as quoted JSON the approver reads, never as text a
terminal interprets, and always shows provenance.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable

import psycopg

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "config", "actions.json")

DDL = """
CREATE TABLE IF NOT EXISTS action_requests (
    id           uuid PRIMARY KEY,
    tool         text NOT NULL,
    class        text NOT NULL,
    args         jsonb NOT NULL,
    provenance   jsonb,
    status       text NOT NULL DEFAULT 'pending',
    dry_run      boolean NOT NULL DEFAULT false,
    requested_at timestamptz NOT NULL DEFAULT now(),
    decided_at   timestamptz,
    result       jsonb,
    trace_id     text
);
"""

# The only legal transitions. Executed/denied/failed rows never mutate —
# the table IS the append-only log (SPEC-P4 §A).
_TRANSITIONS = {
    "pending": {"approved", "denied"},
    "approved": {"executed", "failed"},
}


def load_actions_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ---------- pure policy (offline; pinned by evals/action_set.jsonl) ----------

def policy_decision(tool: str, args: dict, cfg: dict) -> tuple[str, str]:
    """The whole permission ruling as one pure function.
    Returns (verdict, reason): verdict ∈ deny | allow_read |
    require_approval. Order matters — the kill switch outranks
    everything, including reads (SPEC-P4 §A)."""
    if not cfg.get("actions_enabled", False):
        return "deny", "kill switch: actions_enabled is false"
    spec = (cfg.get("tools") or {}).get(tool)
    if spec is None:
        return "deny", f"unknown tool: {tool!r} (not listed = denied)"
    if not spec.get("allowed", False):
        return "deny", f"tool {tool!r} is disallowed by config"
    if not isinstance(args, dict):
        return "deny", "args must be an object"
    missing = [k for k in spec.get("args_required", []) if k not in args]
    if missing:
        return "deny", f"missing required args: {missing}"
    size = len(json.dumps(args))
    limit = cfg.get("max_arg_bytes", 65536)
    if size > limit:
        return "deny", f"args too large: {size} bytes > {limit}"
    if spec["class"] == "read":
        return "allow_read", "read class: auto-allowed, logged"
    return "require_approval", "write class: human approval required (v1)"


def render_approval_payload(request_id: str, tool: str, args: dict,
                            provenance: Any, dry_run: bool) -> str:
    """What the human approver reads. Args and provenance are QUOTED
    DATA (json.dumps) — instruction-shaped text inside them stays inert
    and visible (D12); provenance is always shown so the approver sees
    WHERE the args came from."""
    return json.dumps({
        "action_request": request_id,
        "tool": tool,
        "dry_run": dry_run,
        "args": args,
        "provenance": provenance if provenance is not None else "(none)",
    }, indent=2, ensure_ascii=False)


# ---------- store (SQL; autocommit-guarded like research_state) ----------

class ActionStore:
    """Append-only action log + approval queue. A pending approval is a
    ROW — restart survival is a SELECT, not machinery."""

    def __init__(self, conn: psycopg.Connection):
        if not conn.autocommit:
            raise ValueError(
                "ActionStore requires an autocommit connection — on a "
                "transactional connection the per-action transactions "
                "become savepoints and never commit (the P3 lesson)")
        self.conn = conn

    def ensure_schema(self) -> None:
        with self.conn.transaction():
            self.conn.execute(DDL)

    def create(self, tool: str, klass: str, args: dict, provenance: Any,
               dry_run: bool, status: str = "pending") -> str:
        rid = str(uuid.uuid4())
        with self.conn.transaction():
            self.conn.execute(
                """INSERT INTO action_requests
                   (id, tool, class, args, provenance, status, dry_run)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (rid, tool, klass, json.dumps(args),
                 json.dumps(provenance), status, dry_run))
        return rid

    def _transition(self, rid: str, new_status: str,
                    result: dict | None = None) -> None:
        row = self.conn.execute(
            "SELECT status FROM action_requests WHERE id=%s",
            (rid,)).fetchone()
        if row is None:
            raise KeyError(f"no action request {rid}")
        current = row[0]
        if new_status not in _TRANSITIONS.get(current, set()):
            raise ValueError(
                f"illegal transition {current!r} → {new_status!r} "
                f"(append-only log: settled rows never move)")
        with self.conn.transaction():
            self.conn.execute(
                """UPDATE action_requests SET status=%s, decided_at=now(),
                   result=COALESCE(%s, result) WHERE id=%s""",
                (new_status, json.dumps(result) if result is not None
                 else None, rid))

    def approve(self, rid: str) -> None:
        self._transition(rid, "approved")

    def deny(self, rid: str, reason: str) -> None:
        self._transition(rid, "denied", {"denied_reason": reason})

    def mark_executed(self, rid: str, result: dict) -> None:
        self._transition(rid, "executed", result)

    def mark_failed(self, rid: str, error: str) -> None:
        self._transition(rid, "failed", {"error": error[:500]})

    def load(self, rid: str) -> dict:
        row = self.conn.execute(
            """SELECT tool, class, args, provenance, status, dry_run,
                      result FROM action_requests WHERE id=%s""",
            (rid,)).fetchone()
        if row is None:
            raise KeyError(f"no action request {rid}")
        return {"id": rid, "tool": row[0], "class": row[1], "args": row[2],
                "provenance": row[3], "status": row[4], "dry_run": row[5],
                "result": row[6]}

    def pending(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id FROM action_requests WHERE status='pending'"
            " ORDER BY requested_at").fetchall()
        return [self.load(str(r[0])) for r in rows]


# ---------- dispatch (the broker's one entrance) ----------

def dispatch(store: ActionStore, registry: dict[str, Callable[[dict], dict]],
             tool: str, args: dict, provenance: Any = None,
             approver: Callable[[str], bool] | None = None,
             dry_run: bool = False,
             cfg: dict | None = None) -> dict:
    """Every action enters here; nothing else touches tools (§A
    no-bypass — enforced structurally in T2, by this being the only
    registry holder). Flow: policy → (writes) approval → execute → log.

    dry_run executes EVERYTHING except the final tool call — including
    the approval flow — and stores the would-be request verbatim as the
    result (SPEC-P4 §D contract).
    """
    cfg = cfg or load_actions_config()
    verdict, reason = policy_decision(tool, args, cfg)
    klass = ((cfg.get("tools") or {}).get(tool) or {}).get("class", "?")

    if verdict == "deny":
        rid = store.create(tool, klass, args, provenance, dry_run,
                           status="pending")
        store.deny(rid, reason)
        return store.load(rid)

    rid = store.create(tool, klass, args, provenance, dry_run)

    if verdict == "require_approval":
        if approver is None:
            return store.load(rid)  # queued; a later approval resumes it
        payload = render_approval_payload(rid, tool, args, provenance,
                                          dry_run)
        if not approver(payload):
            store.deny(rid, "human denied")
            return store.load(rid)
        store.approve(rid)
    else:  # allow_read — auto-approved, still logged
        store.approve(rid)

    if dry_run:
        store.mark_executed(rid, {
            "dry_run": True,
            "would_call": {"tool": tool, "args": args},
        })
        return store.load(rid)

    executor = registry.get(tool)
    if executor is None:
        store.mark_failed(rid, f"no executor registered for {tool!r} "
                               "(T1 ships zero tools by design)")
        return store.load(rid)
    try:
        result = executor(args)
    except Exception as exc:
        store.mark_failed(rid, repr(exc))
        raise
    store.mark_executed(rid, result)
    return store.load(rid)


# ---------- MCP registry (P4-T2) — the broker is the SOLE MCP client ----------

def build_registry(tool_names: list[str]) -> dict[str, Callable[[dict], dict]]:
    """Executor callables backed by MCP tool servers. This function is
    the ONLY place in the codebase that touches app.mcp_client — the
    no-bypass import-graph test enforces it. Sessions are per-call
    (spawn → call → close): earned-complexity posture, revisit on
    measured latency."""
    from app.mcp_client import MCPClient  # sole import site (test-pinned)

    def make(name: str) -> Callable[[dict], dict]:
        def call(args: dict) -> dict:
            client = MCPClient(name)
            try:
                return client.call_tool(name, args)
            finally:
                client.close()
        return call

    return {name: make(name) for name in tool_names}
