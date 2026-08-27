"""P4-T2 minimal MCP client — the broker's half of the wire.

IMPORT RULE (no-bypass, test-enforced): the ONLY module allowed to
import this one is `app.broker`. The client spawns the tool's stdio
server as a subprocess, performs the initialize handshake, and speaks
newline-delimited JSON-RPC. One client per tool server; sessions are
short-lived (spawn → call → close) in v1 — connection pooling is
earned complexity."""
from __future__ import annotations

import json
import subprocess
import sys


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, tool_name: str, tool_module: str | None = None):
        cmd = [sys.executable, "-m", "app.mcp_server", tool_name]
        if tool_module:
            cmd += ["--tool-module", tool_module]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1)
        self._id = 0
        init = self._request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "groundwork-broker", "version": "1.0"},
        })
        self.server_info = init.get("serverInfo", {})
        self._notify("notifications/initialized")

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method,
                    "params": params or {}})
        line = self.proc.stdout.readline()
        if not line:
            raise MCPError(f"server closed the pipe during {method!r}")
        reply = json.loads(line)
        if "error" in reply:
            raise MCPError(f"{method}: {reply['error']}")
        return reply["result"]

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def list_tools(self) -> list[dict]:
        return self._request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict) -> dict:
        result = self._request("tools/call",
                               {"name": name, "arguments": arguments})
        text = result["content"][0]["text"]
        if result.get("isError"):
            raise MCPError(f"tool {name!r} errored: {text}")
        return json.loads(text)

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
