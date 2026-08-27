"""related_check — the read-class exemplar tool (SPEC-P4 §B.1).

Wraps the existing /related pipeline seam (app.main.run_related,
extracted P4-T2). Read class: auto-allowed by policy, still logged —
it exists so the action log shows both classes and the broker's read
path is proven on a zero-risk tool first.
"""
from __future__ import annotations

TOOL = {
    "name": "related_check",
    "description": ("Pre-creation coverage check over the owner's "
                    "knowledge base: what already exists on this topic? "
                    "Retrieval only — no generation, no writes."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "top_k": {"type": "integer", "default": 10},
        },
        "required": ["topic"],
    },
}


def execute(args: dict) -> dict:
    from app.main import run_related  # late: services touched only on call
    resp = run_related(args["topic"], int(args.get("top_k", 10)))
    return resp.model_dump()
