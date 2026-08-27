"""P4 tool executors (SPEC-P4 §A/§B).

NO-BYPASS RULE, enforced by tests/test_mcp.py's import-graph proof:
the ONLY module allowed to import `app.tools.*` is `app.mcp_server`
(the stdio host the broker spawns). Every call path runs
caller → broker.dispatch() → MCP client → server subprocess → here.
A second importer of this package is a policy violation and fails CI.
"""
