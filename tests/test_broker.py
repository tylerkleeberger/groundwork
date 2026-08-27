"""P4-T1 offline tests (D16 unmarked) — the action golden set driven
against the pure policy function, plus store-transition and dispatch
contracts over an in-memory store. The live ActionStore roundtrip
(restart survival) is the live-marked test at the bottom.
"""
import json
import pathlib

import pytest

from app.broker import (dispatch, load_actions_config, policy_decision,
                        render_approval_payload)

SET = pathlib.Path(__file__).parent.parent / "evals" / "action_set.jsonl"
CASES = [json.loads(l) for l in SET.read_text().splitlines() if l.strip()]


def apply_overrides(cfg: dict, overrides: dict) -> dict:
    import copy
    cfg = copy.deepcopy(cfg)
    for dotted, val in (overrides or {}).items():
        node = cfg
        keys = dotted.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = val
    return cfg


class MemStore:
    """In-memory mirror of ActionStore's interface + transition rules,
    for dispatch-layer tests (the SQL store's own semantics are pinned
    live)."""
    _TRANSITIONS = {"pending": {"approved", "denied"},
                    "approved": {"executed", "failed"}}

    def __init__(self):
        self.rows = {}
        self.n = 0

    def create(self, tool, klass, args, provenance, dry_run,
               status="pending"):
        self.n += 1
        rid = f"a-{self.n}"
        self.rows[rid] = {"id": rid, "tool": tool, "class": klass,
                          "args": args, "provenance": provenance,
                          "status": status, "dry_run": dry_run,
                          "result": None}
        return rid

    def _move(self, rid, new, result=None):
        cur = self.rows[rid]["status"]
        if new not in self._TRANSITIONS.get(cur, set()):
            raise ValueError(f"illegal transition {cur!r} → {new!r}")
        self.rows[rid]["status"] = new
        if result is not None:
            self.rows[rid]["result"] = result

    def approve(self, rid): self._move(rid, "approved")
    def deny(self, rid, reason): self._move(rid, "denied",
                                            {"denied_reason": reason})
    def mark_executed(self, rid, result): self._move(rid, "executed", result)
    def mark_failed(self, rid, err): self._move(rid, "failed", {"error": err})
    def load(self, rid): return dict(self.rows[rid])
    def pending(self):
        return [dict(r) for r in self.rows.values()
                if r["status"] == "pending"]


# ---------- the action golden set, layer by layer ----------

@pytest.mark.parametrize("case", [c for c in CASES if c["layer"] == "policy"],
                         ids=lambda c: c["id"])
def test_action_set_policy(case):
    cfg = apply_overrides(load_actions_config(),
                          case.get("config_overrides"))
    args = dict(case["args"])
    if case.get("oversize_to_bytes"):
        args["padding"] = "x" * case["oversize_to_bytes"]
    verdict, reason = policy_decision(case["tool"], args, cfg)
    assert verdict == case["expect"], (case["id"], reason)
    if case.get("reason_contains"):
        assert case["reason_contains"] in reason, (case["id"], reason)


def test_action_set_payload_quotes_injection_with_provenance():
    case = [c for c in CASES if c["id"] == "as-010"][0]
    verdict, _ = policy_decision(case["tool"], case["args"],
                                 load_actions_config())
    assert verdict == case["expect"]
    payload = render_approval_payload("rid-1", case["tool"], case["args"],
                                      case["args"]["provenance"], False)
    for needle in case["payload_must_contain"]:
        assert needle in payload, needle
    parsed = json.loads(payload)  # quoted DATA: payload is valid JSON
    assert parsed["args"]["title"].startswith("IGNORE")


def test_action_set_store_transitions():
    store = MemStore()
    rid = store.create("em_draft_kb", "write", {}, None, False)
    store.approve(rid)
    with pytest.raises(ValueError, match="illegal"):
        store.approve(rid)          # as-011: double-approve rejected
    rid2 = store.create("em_draft_kb", "write", {}, None, False)
    store.deny(rid2, "no")
    with pytest.raises(ValueError, match="illegal"):
        store.mark_executed(rid2, {})  # as-012: deny is final


def test_action_set_dispatch_dry_run_contract():
    case = [c for c in CASES if c["id"] == "as-013"][0]
    store, prompts = MemStore(), []

    def approver(payload):
        prompts.append(payload)
        return True

    row = dispatch(store, registry={}, tool=case["tool"], args=case["args"],
                   provenance={"run_id": "r"}, approver=approver,
                   dry_run=True)
    assert row["status"] == "executed" and row["dry_run"] is True
    assert row["result"]["would_call"] == {"tool": case["tool"],
                                           "args": case["args"]}
    assert prompts, "dry-run must still exercise the approval flow"


def test_action_set_read_is_logged():
    store = MemStore()
    row = dispatch(store, registry={"related_check": lambda a: {"ok": 1}},
                   tool="related_check", args={"topic": "x"})
    assert row["status"] == "executed" and row["class"] == "read"
    assert len(store.rows) == 1  # as-014: a row exists for every action


# ---------- dispatch edges beyond the set ----------

def test_denied_action_is_still_logged():
    store = MemStore()
    row = dispatch(store, registry={}, tool="delete_everything", args={})
    assert row["status"] == "denied" and "unknown tool" in \
        row["result"]["denied_reason"]


def test_write_without_approver_queues():
    store = MemStore()
    row = dispatch(store, registry={}, tool="groundwork_sync", args={})
    assert row["status"] == "pending"
    assert store.pending()


def test_human_deny_recorded():
    store = MemStore()
    row = dispatch(store, registry={}, tool="groundwork_sync", args={},
                   approver=lambda p: False)
    assert row["status"] == "denied"
    assert row["result"]["denied_reason"] == "human denied"


def test_zero_tools_by_design_fails_loud():
    store = MemStore()
    row = dispatch(store, registry={}, tool="groundwork_sync", args={},
                   approver=lambda p: True)
    assert row["status"] == "failed"
    assert "zero tools" in row["result"]["error"]


# ---------- live: restart survival (BLUEPRINT acceptance seed) ----------

@pytest.mark.live
def test_action_store_roundtrip_and_restart_survival():
    import os

    import psycopg

    from app.broker import ActionStore
    url = os.environ["APP_DATABASE_URL"]
    with psycopg.connect(url, autocommit=True) as conn:
        store = ActionStore(conn)
        store.ensure_schema()
        rid = store.create("em_draft_kb", "write", {"title": "t"},
                           {"run_id": "r"}, False)
    # "restart": a brand-new connection finds the pending approval
    with psycopg.connect(url, autocommit=True) as conn2:
        store2 = ActionStore(conn2)
        assert any(p["id"] == rid for p in store2.pending())
        store2.approve(rid)
        store2.mark_executed(rid, {"ok": True})
        with pytest.raises(ValueError, match="illegal"):
            store2.approve(rid)
        conn2.execute("DELETE FROM action_requests WHERE id=%s", (rid,))


def test_action_store_refuses_transactional_connection():
    class FakeConn:
        autocommit = False
    from app.broker import ActionStore
    with pytest.raises(ValueError, match="autocommit"):
        ActionStore(FakeConn())


def test_action_set_sync_dry_run_never_spawns():
    """as-015: sync dry-run exercises approval and stores the would-be
    call; the worker subprocess never starts (registry untouched)."""
    case = [c for c in CASES if c["id"] == "as-015"][0]
    store, spawned = MemStore(), []
    row = dispatch(store, {"groundwork_sync":
                           lambda a: spawned.append(a) or {}},
                   case["tool"], case["args"], approver=lambda p: True,
                   dry_run=True)
    assert row["status"] == "executed" and row["result"]["dry_run"]
    assert spawned == []


def test_action_set_em_payload_carries_research_provenance():
    """as-016: the approver always sees WHICH research run produced the
    draft — the EM-seam payload contract."""
    case = [c for c in CASES if c["id"] == "as-016"][0]
    verdict, _ = policy_decision(case["tool"], case["args"],
                                 load_actions_config())
    assert verdict == case["expect"]
    payload = render_approval_payload("rid", case["tool"], case["args"],
                                      case["args"]["provenance"], False)
    for needle in case["payload_must_contain"]:
        assert needle in payload


def test_em_inbox_row_is_always_a_groundwork_draft():
    """The origin/status markers are tool-hardcoded, never
    caller-supplied — a row this tool writes cannot masquerade. Checked
    at SOURCE level (importing app.tools here would violate the
    no-bypass rule this suite itself enforces)."""
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "app" / "tools" /
           "em_draft_kb.py").read_text()
    assert "'groundwork', 'DRAFT'" in src
    assert "origin" not in json.dumps(
        [c["args"] for c in CASES if c.get("tool") == "em_draft_kb"])
