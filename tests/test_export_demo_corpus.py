"""P5-T2: the demo corpus exporter — pure functions only (no network, no clone).

The two properties worth pinning: the output is the SHAPE ingestion already
reads, and the source is PINNED so published numbers stay reproducible.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import export_demo_corpus as ex  # noqa: E402

from ingest import parse_frontmatter  # noqa: E402


def test_the_pin_is_a_commit_sha_not_a_branch():
    """A branch name would make the corpus move under the published numbers.
    Forty hex characters is what cannot drift."""
    assert re.fullmatch(r"[0-9a-f]{40}", ex.PINNED_COMMIT)
    assert ex.PINNED_TAG  # recorded for the reader alongside the sha


def test_source_ids_are_deterministic_and_path_derived():
    first = ex.source_id_for("tutorial/first-steps.md")
    assert first == ex.source_id_for("tutorial/first-steps.md")
    assert first != ex.source_id_for("advanced/first-steps.md")
    assert re.fullmatch(r"[0-9a-f-]{36}", first)


def test_title_prefers_the_h1_and_strips_the_anchor_markup():
    body = "# Query Parameters { #query-parameters }\n\nText."
    assert ex.title_for(body, "tutorial/query-params.md") == "Query Parameters"


def test_title_falls_back_to_a_readable_path_when_there_is_no_heading():
    assert ex.title_for("no heading here", "advanced/sub_app-mounts.md") == "Sub App Mounts"


def test_mkdocs_macro_blocks_are_removed_and_prose_survives():
    raw = "Intro text.\n\n{* ../../docs_src/app/main.py hl[1] *}\n\nClosing text."
    out = ex.strip_mkdocs_macros(raw)
    assert "docs_src" not in out
    assert "Intro text." in out and "Closing text." in out


def test_exported_file_parses_with_INGESTION_OWN_parser_and_carries_the_contract():
    """The shape claim is checked by the reader that actually consumes it."""
    name, content = ex.to_corpus_file(
        "tutorial/first-steps.md",
        "# First Steps { #first-steps }\n\nThe simplest FastAPI file looks like this.",
        "2026-07-29T17:15:38+00:00",
    )
    fields, body = parse_frontmatter(content)
    assert {"source_id", "title", "source_table"} <= set(fields)
    assert fields["title"] == "First Steps"
    assert fields["source_table"] == ex.SOURCE_TABLE
    assert body.startswith("# First Steps")
    assert name.endswith(".md") and fields["source_id"] in name


def test_export_carries_no_clock_reading():
    """updated_at is the PINNED COMMIT's date, so two exports are identical.
    A clock reading here would make the corpus a snapshot instead of a fixture."""
    args = ("tutorial/first-steps.md", "# T\n\nbody", "2026-07-29T17:15:38+00:00")
    assert ex.to_corpus_file(*args) == ex.to_corpus_file(*args)
    fields, _ = parse_frontmatter(ex.to_corpus_file(*args)[1])
    assert fields["updated_at"] == "2026-07-29T17:15:38+00:00"


# ---------- licence + attribution (director ruling, 2026-08-26) ----------

def test_attribution_and_licence_are_written_from_the_pin(tmp_path):
    """Both files are DERIVED from the pin on every run, never maintained
    beside it. Attribution that has to be remembered goes stale the first time
    the pin moves — and stale attribution on redistributed third-party work is
    exactly the error that is embarrassing in public."""
    from export_demo_corpus import PINNED_COMMIT, PINNED_TAG, write_attribution

    work = tmp_path / "clone"
    work.mkdir()
    (work / "LICENSE").write_text("The MIT License (MIT)\n\nCopyright (c) x\n")
    out = tmp_path / "out"
    out.mkdir()

    write_attribution(out, work, "2026-07-29T17:15:38+00:00", 155)

    licence = (out / "LICENSE").read_text()
    assert licence.startswith("The MIT License (MIT)"), "verbatim upstream copy"
    attribution = (out / "ATTRIBUTION.md").read_text()
    assert PINNED_COMMIT in attribution, "the sha must be IN the attribution"
    assert PINNED_TAG in attribution
    assert "FastAPI" in attribution
    assert "https://github.com/fastapi/fastapi.git" in attribution
    assert "MIT" in attribution


def test_export_refuses_when_upstream_licence_is_absent(tmp_path):
    """Redistributing third-party documents without their licence is not a
    warning-level problem. Refuse; shipping a guessed licence is worse than
    failing loudly."""
    from export_demo_corpus import write_attribution

    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(SystemExit, match="REFUSING"):
        write_attribution(out, tmp_path / "no-clone", "2026-01-01T00:00:00+00:00", 1)


def test_ingestion_skips_corpus_metadata_files(tmp_path):
    """ATTRIBUTION.md sits in the corpus directory and ends in .md, so the
    ingester's `*.md` glob would swallow it as a 156th document — one that
    answers questions about licensing. Writer and reader share ONE list."""
    import ingest
    from export_demo_corpus import to_corpus_file

    corpus = tmp_path / "corpus_demo"
    corpus.mkdir()
    name, content = to_corpus_file("tutorial/first-steps.md",
                                   "# First Steps\n\nSome prose about FastAPI.\n",
                                   "2026-07-29T17:15:38+00:00")
    (corpus / name).write_text(content)
    (corpus / "ATTRIBUTION.md").write_text("# Attribution\n\nFastAPI, MIT.\n")
    (corpus / "LICENSE").write_text("The MIT License (MIT)\n")
    (corpus / "MANIFEST.json").write_text("{}\n")

    seen = {f.name for f in sorted(corpus.glob("*.md"))
            if f.name not in ingest.CORPUS_METADATA_FILES}
    assert seen == {name}, f"metadata leaked into the document set: {seen}"
    assert "ATTRIBUTION.md" in ingest.CORPUS_METADATA_FILES
    assert "LICENSE" in ingest.CORPUS_METADATA_FILES
