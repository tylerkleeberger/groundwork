"""P4-T3 CLI approval — the §E ruling: the human approves where the
human already works. No new surface, no new auth; the terminal renders
the approval payload as QUOTED JSON (D12 — instruction-shaped args stay
inert and visible).

Usage (from repo root, .env loaded):
  .venv/bin/python scripts/actions.py request <tool> [--args '<json>'] [--dry-run]
  .venv/bin/python scripts/actions.py pending
  .venv/bin/python scripts/actions.py approve <request_id>
  .venv/bin/python scripts/actions.py deny <request_id> [reason]

`request` queues (writes) or executes (reads/denials are immediate).
`approve` is the human gate: shows the payload, asks y/N on the
terminal, then executes through the broker registry and prints the
result. Everything lands in the append-only action log either way.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402

from app.broker import (ActionStore, build_registry, dispatch,  # noqa: E402
                        load_actions_config, render_approval_payload)


def _store(conn) -> ActionStore:
    store = ActionStore(conn)
    store.ensure_schema()
    return store


def cmd_request(store: ActionStore, tool: str, args: dict,
                dry_run: bool) -> int:
    registry = build_registry([tool])
    row = dispatch(store, registry, tool, args,
                   provenance=args.get("provenance"), dry_run=dry_run)
    print(f"{row['id']}  {row['tool']}  → {row['status']}")
    if row["status"] == "pending":
        print("queued for approval: scripts/actions.py approve", row["id"])
    elif row["result"]:
        print(json.dumps(row["result"], indent=2, default=str)[:2000])
    return 0 if row["status"] in ("pending", "executed") else 1


def cmd_pending(store: ActionStore) -> int:
    rows = store.pending()
    if not rows:
        print("no pending actions")
        return 0
    for r in rows:
        print(f"{r['id']}  {r['tool']}  class={r['class']}"
              f"  dry_run={r['dry_run']}")
    return 0


def cmd_approve(store: ActionStore, rid: str) -> int:
    row = store.load(rid)
    if row["status"] != "pending":
        print(f"{rid} is {row['status']!r}, not pending")
        return 1
    print(render_approval_payload(rid, row["tool"], row["args"],
                                  row["provenance"], row["dry_run"]))
    if not sys.stdin.isatty():
        # a non-TTY stdin cannot carry a human decision — leave the
        # request PENDING and say so (deny would burn a queued action
        # on a plumbing accident; approval NEEDS a real terminal)
        print("\nstdin is not a TTY — approval requires an interactive "
              "terminal. Request left pending.")
        return 1
    if input("\napprove this action? [y/N] ").strip().lower() != "y":
        store.deny(rid, "human denied at CLI")
        print("denied")
        return 0
    store.approve(rid)
    if row["dry_run"]:
        store.mark_executed(rid, {"dry_run": True, "would_call": {
            "tool": row["tool"], "args": row["args"]}})
        print("dry run recorded — nothing executed")
        return 0
    registry = build_registry([row["tool"]])
    try:
        result = registry[row["tool"]](row["args"])
    except Exception as exc:
        store.mark_failed(rid, repr(exc))
        print("FAILED:", exc)
        return 1
    store.mark_executed(rid, result)
    print(json.dumps(result, indent=2, default=str)[:2000])
    return 0


def cmd_deny(store: ActionStore, rid: str, reason: str) -> int:
    store.deny(rid, reason or "human denied at CLI")
    print("denied")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    with psycopg.connect(os.environ["APP_DATABASE_URL"],
                         autocommit=True) as conn:
        store = _store(conn)
        cmd = argv[0]
        if cmd == "request":
            args = json.loads(argv[argv.index("--args") + 1]) \
                if "--args" in argv else {}
            return cmd_request(store, argv[1], args, "--dry-run" in argv)
        if cmd == "pending":
            return cmd_pending(store)
        if cmd == "approve":
            return cmd_approve(store, argv[1])
        if cmd == "deny":
            return cmd_deny(store, argv[1],
                            " ".join(argv[2:]))
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
