"""Offline tests for export_corpus.py pure logic (D16: unmarked = no
services, no tokens, runs anywhere)."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from export_corpus import (  # noqa: E402
    assemble_sections,
    document,
    emkb_to_file,
    emsession_to_file,
    filename_for,
    frontmatter,
)


def test_filename_is_deterministic_and_lowercased():
    assert filename_for("EmKb", "abc123") == "emkb-abc123.md"
    assert filename_for("EmKb", "abc123") == filename_for("EmKb", "abc123")


def test_filename_sanitizes_path_escapes():
    assert "/" not in filename_for("EmKb", "../../etc/passwd")
    assert filename_for("KbUnit", "a/b\\c") == "kbunit-a-b-c.md"


def test_frontmatter_survives_yaml_hostile_titles():
    fm = frontmatter({"title": 'Ask: the "why" — a: b', "source_table": "EmKb"})
    assert fm.startswith("---\n") and fm.endswith("---\n")
    # JSON-encoded string is a valid YAML scalar; raw colon must not leak
    assert 'title: "Ask: the \\"why\\" — a: b"' in fm


def test_frontmatter_renders_datetime_iso_and_none_empty():
    fm = frontmatter({"updated_at": datetime(2026, 7, 4, 12, 30), "domain": None})
    assert "updated_at: 2026-07-04T12:30:00" in fm
    assert 'domain: ""' in fm


def test_assemble_single_section_has_no_heading():
    assert assemble_sections([("Body", "hello")]) == "hello\n"


def test_assemble_multi_section_skips_empty_and_headings_present():
    out = assemble_sections([("Decisions", "did X"), ("Notes", "  ")])
    assert out == "did X\n"  # empty Notes dropped -> single section, no heading
    out2 = assemble_sections([("Decisions", "did X"), ("Notes", "note Y")])
    assert "## Decisions" in out2 and "## Notes" in out2


def test_emkb_row_skips_empty_body():
    row = {"id": "x", "concept": "t", "kbType": "Concept", "status": "DRAFT",
           "body": "   ", "updatedAt": datetime(2026, 1, 1), "domain": "D", "layer": "L"}
    assert emkb_to_file(row) is None


def test_emkb_row_maps_all_fields():
    row = {"id": "x1", "concept": "Title", "kbType": "Concept", "status": "DRAFT",
           "body": "content", "updatedAt": datetime(2026, 1, 1), "domain": "D", "layer": "L"}
    fname, content = emkb_to_file(row)
    assert fname == "emkb-x1.md"
    for needle in ('source_id: "x1"', 'source_table: "EmKb"', 'kb_type: "Concept"',
                   'domain: "D"', 'layer: "L"', "updated_at: 2026-01-01T00:00:00"):
        assert needle in content
    assert content.rstrip().endswith("content")


def test_emsession_uses_createdat_as_updated_at():
    row = {"id": "s1", "topic": "T", "date": datetime(2026, 2, 2),
           "createdAt": datetime(2026, 3, 3), "decisions": "d", "notes": "n",
           "domain": "D"}
    _, content = emsession_to_file(row)
    assert "updated_at: 2026-03-03T00:00:00" in content
    assert "session_date: 2026-02-02T00:00:00" in content


def test_document_is_frontmatter_then_blank_line_then_body():
    doc = document({"title": "t"}, "body\n")
    assert doc == '---\ntitle: "t"\n---\n\nbody\n'
