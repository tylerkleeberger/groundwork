"""P4-T4 injection-attempt detector (SPEC-P4 §D.3, D12).

The STRUCTURAL defense is that no generated text can reach dispatch():
the research/ask pipelines have no tool-calling path, and the broker is
the only door (import-graph proof). This module adds the OBSERVABILITY
half the spec requires — "the attempt shape is visible in the log":
retrieved chunks and generated answers are scanned for action-directive
shapes, and any hit is recorded in the append-only action log as a
DENIED row that was never dispatched.

Pure detection (offline-pinned); the logging half needs a store.

Semantics of a detection row, stated so the log stays honest:
  status=denied · result.denied_reason names the detector · provenance
  carries WHERE the text came from. A detection row means "content
  named a tool"; it does NOT mean anything was requested — nothing
  reached the broker's entrance, which is the point.
"""
from __future__ import annotations

import re
from typing import Any

# Directive shapes: an imperative verb near a known tool name. Kept
# deliberately narrow — a detector that fires on every mention of a
# tool name would drown the log and train its readers to ignore it.
_VERBS = r"(?:call|invoke|run|execute|use|trigger|please)"
_WINDOW = 80


def detect_directives(text: str, tool_names: list[str]) -> list[dict]:
    """Find action-directive shapes naming a known tool. Returns one
    finding per (tool, match), each with the surrounding excerpt so a
    human reading the log sees the shape, not just a boolean."""
    findings: list[dict] = []
    if not text:
        return findings
    low = text.lower()
    for tool in tool_names:
        for m in re.finditer(re.escape(tool.lower()), low):
            start = max(0, m.start() - _WINDOW)
            window = low[start:m.start()]
            if re.search(_VERBS + r"[^.]{0,40}$", window):
                findings.append({
                    "tool": tool,
                    "excerpt": text[start:min(len(text),
                                              m.end() + _WINDOW)].strip(),
                })
                break  # one finding per tool per text — no flooding
    return findings


def scan_payload(chunks: list[dict], answer: str,
                 tool_names: list[str]) -> list[dict]:
    """Scan both sides of a generation: what retrieval SHOWED the model
    and what the model WROTE. Chunk findings carry their source_id."""
    findings = []
    for c in chunks or []:
        for f in detect_directives(c.get("content", ""), tool_names):
            findings.append({**f, "where": "retrieved_chunk",
                             "source_id": c.get("source_id")})
    for f in detect_directives(answer or "", tool_names):
        findings.append({**f, "where": "generated_answer"})
    return findings


def log_attempts(store: Any, findings: list[dict],
                 context: dict | None = None) -> list[str]:
    """Record each finding as a denied, never-dispatched row in the
    append-only action log. Returns the row ids."""
    ids = []
    for f in findings:
        rid = store.create(
            f["tool"], "write", {"_detected_text": f["excerpt"]},
            {"detector": "injection_directive_scan",
             "where": f.get("where"), "source_id": f.get("source_id"),
             **(context or {})},
            False)
        store.deny(rid, "INJECTION ATTEMPT: action-directive text found "
                        "in model-facing content; never dispatched "
                        "(no tool-calling path exists from generation)")
        ids.append(rid)
    return ids
