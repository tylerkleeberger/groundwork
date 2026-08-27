"""P4-T2 offline tests (D16 unmarked) — MCP protocol logic, the real
subprocess roundtrip via the echo fixture (no services), broker→MCP
dispatch, and THE NO-BYPASS IMPORT-GRAPH PROOF (BLUEPRINT §P4
acceptance: no code path reaches a tool around the broker).

The live-marked test at the bottom drives related_check end-to-end
through dispatch() against real services.
"""
import ast
import json
import pathlib

import pytest

from app.broker import dispatch
from app.mcp_server import handle_message
from tests.test_broker import MemStore

REPO = pathlib.Path(__file__).resolve().parent.parent
ECHO = {"tool_name": "echo", "tool_module": "tests.echo_tool"}


# ---------- protocol logic (pure) ----------

def _tool():
    from tests.echo_tool import TOOL, execute
    return TOOL, execute


def test_initialize_and_list():
    tool, execute = _tool()
    init = handle_message({"jsonrpc": "2.0", "id": 1,
                           "method": "initialize", "params": {}},
                          tool, execute)
    assert init["result"]["protocolVersion"]
    assert init["result"]["capabilities"] == {"tools": {}}
    assert handle_message({"jsonrpc": "2.0",
                           "method": "notifications/initialized"},
                          tool, execute) is None
    listed = handle_message({"jsonrpc": "2.0", "id": 2,
                             "method": "tools/list"}, tool, execute)
    assert listed["result"]["tools"] == [tool]


def test_call_success_error_and_unknowns():
    tool, execute = _tool()
    ok = handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "echo",
                                    "arguments": {"a": 1}}}, tool, execute)
    assert not ok["result"]["isError"]
    assert json.loads(ok["result"]["content"][0]["text"]) == {"echoed": {"a": 1}}
    boom = handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                           "params": {"name": "echo",
                                      "arguments": {"boom": True}}},
                          tool, execute)
    assert boom["result"]["isError"]  # tool errors are results, not crashes
    wrong = handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                            "params": {"name": "other", "arguments": {}}},
                           tool, execute)
    assert wrong["error"]["code"] == -32602
    missing = handle_message({"jsonrpc": "2.0", "id": 6,
                              "method": "nope"}, tool, execute)
    assert missing["error"]["code"] == -32601


# ---------- the real wire (subprocess, still offline) ----------

def test_stdio_roundtrip_with_real_subprocess():
    from app.mcp_client import MCPClient, MCPError
    client = MCPClient(**{"tool_name": ECHO["tool_name"],
                          "tool_module": ECHO["tool_module"]})
    try:
        assert client.server_info["name"] == "groundwork-echo"
        tools = client.list_tools()
        assert tools[0]["name"] == "echo"
        assert client.call_tool("echo", {"x": "y"}) == {"echoed": {"x": "y"}}
        with pytest.raises(MCPError, match="fixture explosion"):
            client.call_tool("echo", {"boom": True})
    finally:
        client.close()


def test_dispatch_through_mcp_offline():
    """caller → dispatch → (approval) → MCP subprocess → result — the
    whole §A path with zero services, via a registry entry built the
    same way build_registry builds them."""
    from app.mcp_client import MCPClient

    def echo_executor(args):
        client = MCPClient("echo", tool_module="tests.echo_tool")
        try:
            return client.call_tool("echo", args)
        finally:
            client.close()

    store = MemStore()
    cfg = {"actions_enabled": True, "max_arg_bytes": 65536,
           "tools": {"echo": {"class": "write", "allowed": True,
                              "args_required": []}}}
    row = dispatch(store, {"echo": echo_executor}, "echo", {"m": 1},
                   approver=lambda p: True, cfg=cfg)
    assert row["status"] == "executed"
    assert row["result"] == {"echoed": {"m": 1}}


# ---------- THE NO-BYPASS PROOF (BLUEPRINT §P4 acceptance) ----------

ALLOWED_TOOL_IMPORTERS = {"app/mcp_server.py"}      # the stdio host
ALLOWED_CLIENT_IMPORTERS = {"app/broker.py"}        # the sole MCP client


def _imports_of(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{a.name}" for a in node.names}
    return found


def test_no_bypass_import_graph():
    """No module outside the broker imports a tool executor or the MCP
    client. AST-walked over every tracked .py in the repo — a second
    importer fails CI, which is how 'no code path reaches a tool around
    the broker' is a PROOF, not a promise."""
    violations = []
    for path in REPO.rglob("*.py"):
        rel = str(path.relative_to(REPO))
        if rel.startswith((".venv", "corpus", ".git")):
            continue
        imports = _imports_of(path)
        if any(i == "app.tools" or i.startswith("app.tools.")
               for i in imports) and rel not in ALLOWED_TOOL_IMPORTERS:
            violations.append(f"{rel} imports app.tools")
        if any(i == "app.mcp_client" or i.startswith("app.mcp_client.")
               for i in imports) and rel not in ALLOWED_CLIENT_IMPORTERS \
                and rel != "tests/test_mcp.py":
            violations.append(f"{rel} imports app.mcp_client")
    assert not violations, violations


def test_no_bypass_registry_covers_registered_tools():
    """Every tool the server will host is config-declared — no ghost
    tools reachable by wire that policy has never heard of."""
    from app.broker import load_actions_config
    from app.mcp_server import REGISTERED
    declared = set(load_actions_config()["tools"])
    assert set(REGISTERED) <= declared


# ---------- live: the read exemplar end-to-end ----------

@pytest.mark.live
def test_related_check_through_broker_live():
    import os

    import psycopg

    from app.broker import ActionStore, build_registry
    with psycopg.connect(os.environ["APP_DATABASE_URL"],
                         autocommit=True) as conn:
        store = ActionStore(conn)
        store.ensure_schema()
        registry = build_registry(["related_check"])
        row = dispatch(store, registry, "related_check",
                       {"topic": "SMACSS"})
        assert row["status"] == "executed" and row["class"] == "read"
        assert row["result"]["verdict"] in ("likely covered",
                                            "adjacent material",
                                            "nothing close")
        assert row["result"]["sources"]
        conn.execute("DELETE FROM action_requests WHERE id=%s",
                     (row["id"],))
