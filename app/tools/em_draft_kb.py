"""em_draft_kb — write-class tool, EXTERNAL (SPEC-P4 §B.3; credentials
per ratified Option B).

Writes a clearly-marked DRAFT row into the owner's EM staging inbox
(`groundwork_inbox` — the ONLY table the INSERT-only `groundwork_writer`
role can touch). A draft row is an INBOX ITEM, never a published entry:
the owner's promotion step is the editorial gate (strategic direction 1).

Credential: APP_EM_WRITER_URL (D13 prefix; owner-provisioned per the T3
owner block; double-quoted in .env; never printed). This module is the
only reader of that variable, and this module is only importable by the
MCP server host — the import-graph proof carries the credential rule.
"""
from __future__ import annotations

import json
import os

TOOL = {
    "name": "em_draft_kb",
    "description": ("Draft a new KB entry into the owner's EM as a "
                    "clearly-marked DRAFT inbox row (origin=groundwork). "
                    "The owner promotes or deletes it — editorial "
                    "authority stays with the EM."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body_markdown": {"type": "string"},
            "provenance": {"type": "object"},
        },
        "required": ["title", "body_markdown", "provenance"],
    },
}


def inbox_row(args: dict) -> tuple[str, tuple]:
    """SQL + params for the draft row — pure, offline-pinned. The
    origin/status markers are hardcoded here, not caller-supplied: a
    row this tool writes is ALWAYS a groundwork DRAFT."""
    return (
        """INSERT INTO groundwork_inbox
           (title, body_markdown, provenance, origin, status)
           VALUES (%s, %s, %s, 'groundwork', 'DRAFT')
           RETURNING id, created_at""",
        (args["title"], args["body_markdown"],
         json.dumps(args["provenance"])),
    )


def execute(args: dict) -> dict:
    import psycopg  # late: import cost only on call
    url = os.environ.get("APP_EM_WRITER_URL")
    if not url:
        raise RuntimeError("APP_EM_WRITER_URL is not set — the owner's "
                           "Neon block has not been executed (T3 §2)")
    sql, params = inbox_row(args)
    with psycopg.connect(url, autocommit=True) as conn:
        row = conn.execute(sql, params).fetchone()
    return {"inbox_id": str(row[0]), "created_at": str(row[1]),
            "status": "DRAFT", "origin": "groundwork"}
