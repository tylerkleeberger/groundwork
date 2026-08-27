"""P4-T2 minimal MCP server host — stdio transport, newline-delimited
JSON-RPC 2.0, the conformant core of the Model Context Protocol:
initialize / notifications/initialized / tools/list / tools/call.

Hand-rolled on stdlib BY DECISION, not accident: the ratified spec
commits to the PROTOCOL (Q02 — a tool is inspectable/swappable via a
standard wire format), not to an SDK; a dependency would have tripped
the T2 STOP rule, and the wire subset a single-tool server needs is
small enough to own and test to the last branch (D1). Adopting the
official SDK later is a one-module swap behind the same broker seam.

Usage (spawned BY THE BROKER, never run ad hoc):
  python -m app.mcp_server <tool_name> [--tool-module dotted.path]

The hosted tool module exposes TOOL (name/description/inputSchema) and
execute(args) -> dict. app.tools.* may only be imported HERE — the
no-bypass import-graph test enforces it.
"""
from __future__ import annotations

import importlib
import json
import sys

PROTOCOL_VERSION = "2025-06-18"

REGISTERED = {
    "related_check": "app.tools.related_check",
    "groundwork_sync": "app.tools.groundwork_sync",
    "em_draft_kb": "app.tools.em_draft_kb",
}


def _rpc_result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _rpc_error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message}}


def handle_message(msg: dict, tool: dict, execute) -> dict | None:
    """Pure protocol logic (offline-tested): one request in, one
    response out; None for notifications."""
    method = msg.get("method")
    msg_id = msg.get("id")
    if method == "initialize":
        return _rpc_result(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": f"groundwork-{tool['name']}",
                           "version": "1.0"},
        })
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _rpc_result(msg_id, {"tools": [tool]})
    if method == "tools/call":
        params = msg.get("params") or {}
        if params.get("name") != tool["name"]:
            return _rpc_error(msg_id, -32602,
                              f"unknown tool {params.get('name')!r}")
        try:
            result = execute(params.get("arguments") or {})
        except Exception as exc:  # tool errors are results, not crashes
            return _rpc_result(msg_id, {
                "content": [{"type": "text", "text": repr(exc)}],
                "isError": True,
            })
        return _rpc_result(msg_id, {
            "content": [{"type": "text",
                         "text": json.dumps(result, default=str)}],
            "isError": False,
        })
    if msg_id is None:
        return None  # unknown notification: ignore per JSON-RPC
    return _rpc_error(msg_id, -32601, f"method not found: {method!r}")


def serve(tool_module_path: str) -> int:
    mod = importlib.import_module(tool_module_path)
    tool, execute = mod.TOOL, mod.execute
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps(_rpc_error(None, -32700, "parse error")),
                  flush=True)
            continue
        reply = handle_message(msg, tool, execute)
        if reply is not None:
            print(json.dumps(reply, default=str), flush=True)
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("usage: python -m app.mcp_server <tool_name> "
              "[--tool-module dotted.path]", file=sys.stderr)
        return 2
    name = args[0]
    if "--tool-module" in args:  # test fixture hook
        module_path = args[args.index("--tool-module") + 1]
    else:
        module_path = REGISTERED.get(name)
        if module_path is None:
            print(f"unknown tool {name!r}", file=sys.stderr)
            return 2
    return serve(module_path)


if __name__ == "__main__":
    sys.exit(main())
