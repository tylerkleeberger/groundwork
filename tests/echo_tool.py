"""Offline MCP test fixture: an echo tool with zero service needs.
Hosted by app.mcp_server via --tool-module (the test hook); lives
OUTSIDE app.tools so the import-graph rule stays clean."""
TOOL = {
    "name": "echo",
    "description": "test fixture: returns its arguments",
    "inputSchema": {"type": "object", "properties": {"boom": {}},
                    "required": []},
}


def execute(args: dict) -> dict:
    if args.get("boom"):
        raise RuntimeError("fixture explosion")
    return {"echoed": args}
