"""Offline tests for scripts/sync.py pure logic (D16 unmarked: no services,
no tokens). T9's dispatch constraint names the three decisions that must be
offline-tested: prune-set computation, summary assembly, pin-check decision.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ingest import EMBED_DIMS, EMBED_MODEL_ID  # noqa: E402
from sync import (  # noqa: E402
    PIN_WANT,
    compute_prune_set,
    failure_banner,
    format_summary,
    pin_refusal,
)


# ---------- prune-set computation ----------

def test_prune_removes_files_whose_rows_vanished():
    disk = {"emkb-a.md", "emkb-b.md", "kbunit-c.md"}
    exported = {"emkb-a.md", "kbunit-c.md"}
    assert compute_prune_set(disk, exported) == ["emkb-b.md"]


def test_prune_is_empty_on_no_change():
    files = {"emkb-a.md", "emsession-b.md"}
    assert compute_prune_set(files, set(files)) == []


def test_prune_ignores_newly_exported_files_not_yet_on_disk_snapshot():
    # New rows appear in the export set; nothing on disk becomes stale.
    disk = {"emkb-a.md"}
    exported = {"emkb-a.md", "emkb-new.md"}
    assert compute_prune_set(disk, exported) == []


def test_prune_is_sorted_and_deterministic():
    disk = {"z.md", "a.md", "m.md"}
    assert compute_prune_set(disk, set()) == ["a.md", "m.md", "z.md"]


# ---------- pin-check decision (D17 refuse-to-mix, pre-flight) ----------

def test_pin_fresh_db_proceeds():
    # Missing table (None) or empty rows: ingest.check_meta initializes pins.
    assert pin_refusal(None) is None
    assert pin_refusal({}) is None


def test_pin_match_proceeds():
    assert pin_refusal(dict(PIN_WANT)) is None
    assert PIN_WANT == {"embedding_model": EMBED_MODEL_ID,
                        "dimensions": str(EMBED_DIMS)}


def test_pin_model_mismatch_refuses_loudly_with_both_values():
    msg = pin_refusal({"embedding_model": "other-model",
                       "dimensions": str(EMBED_DIMS)})
    assert msg is not None and "REFUSING" in msg
    assert "other-model" in msg and EMBED_MODEL_ID in msg


def test_pin_dimension_mismatch_refuses():
    msg = pin_refusal({"embedding_model": EMBED_MODEL_ID, "dimensions": "1536"})
    assert msg is not None and "REFUSING" in msg and "1536" in msg


def test_pin_extra_or_missing_keys_refuse():
    # Anything other than the exact pin set is a mismatch, not a guess.
    assert pin_refusal({"embedding_model": EMBED_MODEL_ID}) is not None
    assert pin_refusal({**PIN_WANT, "stray": "x"}) is not None


# ---------- summary assembly ----------

def test_summary_has_one_line_per_stage_with_counts():
    out = format_summary([
        ("export", {"total": 567, "skipped_empty": 5}),
        ("prune", {"pruned": 2, "files": ["emkb-x.md", "emkb-y.md"]}),
        ("ingest", {"embedded": 2, "unchanged": 565, "deleted": 2}),
    ])
    lines = out.splitlines()
    assert lines[0] == "sync summary:"
    assert len(lines) == 4
    assert "export" in lines[1] and "total=567" in lines[1]
    assert "prune" in lines[2] and "pruned=2" in lines[2]
    assert "ingest" in lines[3] and "unchanged=565" in lines[3]


def test_summary_of_noop_run_reads_as_noop():
    out = format_summary([
        ("export", {"total": 567, "skipped_empty": 5}),
        ("prune", {"pruned": 0, "files": []}),
        ("ingest", {"embedded": 0, "unchanged": 567, "deleted": 0}),
    ])
    assert "pruned=0" in out and "embedded=0" in out and "deleted=0" in out


# ---------- failure banner (never a silent partial sync) ----------

def test_failure_banner_names_stage_and_cause_unmissably():
    banner = failure_banner("ingest", "ConnectionError: gateway down")
    assert "SYNC FAILED" in banner and "'ingest'" in banner
    assert "gateway down" in banner
    assert banner.startswith("#" * 64) and banner.endswith("#" * 64)
