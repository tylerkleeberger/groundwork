"""Offline tests for ingest.py pure logic (D16 unmarked: no services, no
tokens). The frontmatter tests use scripts/export_corpus.py as the writer —
the parser and writer must stay symmetric."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from export_corpus import document, frontmatter  # noqa: E402
from ingest import (  # noqa: E402
    TOKEN_MAX,
    chunk_body,
    chunk_records,
    estimate_tokens,
    file_hash,
    parse_frontmatter,
    split_sentences,
)


def test_frontmatter_roundtrip_with_export_writer():
    doc = document(
        {"source_id": "x1", "title": 'Ask: the "why"', "updated_at": datetime(2026, 1, 2),
         "source_table": "EmKb", "domain": "D", "layer": None},
        "Body text.\n",
    )
    fields, body = parse_frontmatter(doc)
    assert fields["source_id"] == "x1"
    assert fields["title"] == 'Ask: the "why"'
    assert fields["updated_at"] == "2026-01-02T00:00:00"
    assert fields["layer"] == ""
    assert body == "Body text.\n"


def test_parse_without_frontmatter_returns_body_unchanged():
    fields, body = parse_frontmatter("just text")
    assert fields == {} and body == "just text"


def test_headings_are_hard_boundaries():
    body = "# A\n\n" + ("alpha. " * 30) + "\n\n# B\n\n" + ("beta. " * 30)
    chunks = chunk_body(body)
    sections = {c.section for c in chunks}
    assert sections == {"A", "B"}
    for c in chunks:
        assert ("alpha" in c.content) != ("beta" in c.content)  # never mixed


def test_small_section_stays_one_chunk_below_minimum():
    chunks = chunk_body("# Tiny\n\nJust one line.")
    assert len(chunks) == 1
    assert chunks[0].content == "Just one line."


def test_chunks_respect_max_and_never_split_mid_sentence():
    sentences = [f"Sentence number {i} has exactly this many words in it." for i in range(120)]
    body = " ".join(sentences)  # one giant paragraph, forces sentence fallback
    chunks = chunk_body(body)
    assert len(chunks) > 1
    rebuilt = " ".join(" ".join(c.content.split("\n\n")) for c in chunks)
    for s in sentences:
        assert s in rebuilt  # every sentence survives whole
    for c in chunks:
        assert c.token_estimate <= TOKEN_MAX + estimate_tokens(sentences[0])


def test_oversized_single_sentence_stays_whole():
    monster = "word " * 5000
    chunks = chunk_body(monster.strip() + ".")
    assert len(chunks) == 1  # never mid-sentence, even past the max


def test_heading_flush_resets_accumulator():
    # regression: a stale accumulator after a heading boundary over-fragments
    # everything downstream (caught live: 4179 -> 3272 chunks on the corpus)
    big = "Word word word here. " * 250
    small = "Small sentence here. " * 10
    chunks = chunk_body(big.strip() + "\n\n# B\n\n" + small.strip())
    assert len([c for c in chunks if c.section == "B"]) == 1


def test_chunk_indexes_are_sequential():
    body = "# A\n\n" + ("para. " * 200) + "\n\n# B\n\ntail."
    chunks = chunk_body(body)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunk_records_carry_frontmatter_metadata():
    doc = document(
        {"source_id": "s1", "title": "T", "updated_at": datetime(2026, 1, 1),
         "source_table": "EmKb", "kb_type": "Concept", "status": "DRAFT",
         "domain": "Dom", "layer": "L1"},
        "# H\n\nSome content here.",
    )
    records = chunk_records("emkb-s1.md", doc.encode())
    assert len(records) == 1
    r = records[0]
    assert r["source_id"] == "s1" and r["domain"] == "Dom" and r["layer"] == "L1"
    assert r["file_path"] == "emkb-s1.md" and r["section"] == "H"
    assert "kb_type" not in r  # only the spec'd per-chunk metadata keys


def test_file_hash_is_stable_and_content_sensitive():
    assert file_hash(b"abc") == file_hash(b"abc")
    assert file_hash(b"abc") != file_hash(b"abd")


def test_split_sentences_handles_terminators():
    parts = split_sentences("One. Two! Three? Four… Five.")
    assert len(parts) == 5
