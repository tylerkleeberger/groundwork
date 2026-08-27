"""groundwork_sync — write-class tool (SPEC-P4 §B.2).

Triggers the existing corpus sync worker (scripts/sync.py, P1-T9:
export → prune → ingest, idempotent, pin-guarded). Lowest-risk write in
the system — its blast radius is this app's own DB behind its own
refuse-to-mix pin — but STILL approval-gated in v1: the gate pattern is
uniform or it is nothing.

Runs the worker as a subprocess: sync's contract IS its CLI (exit 0 =
clean, 1 = stage failure with banner, 2 = pin refusal before any stage
touched anything). The tool reports the exit code and the output tail —
the worker's own summary — verbatim.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent

TOOL = {
    "name": "groundwork_sync",
    "description": ("Run the corpus sync worker (export → prune → "
                    "ingest) over the owner's knowledge base. "
                    "Idempotent; refuses on embedding-pin mismatch."),
    "inputSchema": {"type": "object", "properties": {}, "required": []},
}


def execute(args: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "sync.py")],
        capture_output=True, text=True, timeout=600, cwd=str(REPO))
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-15:])
    return {"exit_code": proc.returncode,
            "clean": proc.returncode == 0,
            "summary_tail": tail,
            "stderr_tail": "\n".join(
                (proc.stderr or "").strip().splitlines()[-5:])}
