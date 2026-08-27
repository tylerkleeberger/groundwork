"""P1-T9 ingestion sync worker: one-command source-of-truth sync, safe on a
schedule. Runs export -> prune -> ingest end-to-end:

- export: scripts/export_corpus.run_export re-exports from
  APP_CORPUS_SOURCE_URL (overwrites in place, never deletes);
- prune: corpus/*.md files whose rows no longer exist in the export set are
  removed (learned at the 2026-07-12 Neon cleanup: stale files linger
  without this);
- ingest: ingest.run_ingest re-embeds only deltas via the hash ledger and
  cascades deletions of pruned files' chunks.

T9 ruling (2026-07-13): idempotent (a second run with no source changes is
a no-op); every run prints a per-stage summary AND logs a sync summary
trace to Langfuse; ANY stage failure -> nonzero exit with an unmissable
message (never a silent partial sync); REFUSES to run — before touching
anything — if ingest_meta's embedding_model/dimensions mismatch the code's
pin (D17 refuse-to-mix, surfaced loudly).

Stage order is load-bearing: prune runs only after export COMPLETED, so a
mid-export failure can never delete files based on a partial export set;
ingest runs after prune so its deletion sweep cascades the pruned files'
chunks out of the DB in the same run.

Exit codes: 0 = synced; 1 = stage or trace failure; 2 = refused before
touching anything (pin mismatch or missing environment).

Run: set -a; source .env; set +a; python scripts/sync.py
Offline tests for the pure logic: tests/test_sync.py (D16 unmarked).
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))            # ingest.py lives at repo root
sys.path.insert(0, str(REPO_ROOT / "scripts"))  # export_corpus, when run elsewhere

from app.profile import load_profile  # noqa: E402
from export_corpus import CORPUS_DIR, run_export  # noqa: E402
from ingest import EMBED_DIMS, EMBED_MODEL_ID, run_ingest  # noqa: E402

# Langfuse host default deliberately NOT applied here: the SDK's fallback is
# cloud.langfuse.com, and a scheduled sync silently tracing to the wrong
# host is exactly the failure mode this worker must refuse.
REQUIRED_ENV = (
    "APP_CORPUS_SOURCE_URL",
    "APP_DATABASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
)

PIN_WANT = {"embedding_model": EMBED_MODEL_ID, "dimensions": str(EMBED_DIMS)}


# ---------- pure logic (offline-tested in tests/test_sync.py) ----------

def compute_prune_set(disk_files: set[str], exported_files: set[str]) -> list[str]:
    """corpus/*.md present on disk but absent from this run's export set —
    their source rows no longer exist. Sorted for deterministic output."""
    return sorted(disk_files - exported_files)


def pin_refusal(db_pins: dict[str, str] | None,
                want: dict[str, str] = PIN_WANT) -> str | None:
    """The refuse-to-mix decision (D17), computed before any stage runs.
    None -> safe to proceed. A string -> the refusal message to print.
    A missing table or empty rows means a fresh DB: ingest.check_meta
    initializes the pins itself, so sync proceeds."""
    if not db_pins:
        return None
    if db_pins == want:
        return None
    return (
        "REFUSING TO SYNC (before touching anything): ingest_meta pin "
        f"mismatch.\n  DB has:     {db_pins}\n  code wants: {want}\n"
        "Changing embedding models requires a deliberate full re-embed (D17); "
        "a scheduled sync must never mix embeddings silently."
    )


def format_summary(stages: list[tuple[str, dict]]) -> str:
    """Per-stage summary block, one line per stage (T9: printed every run
    and attached verbatim to the Langfuse sync trace)."""
    lines = ["sync summary:"]
    for name, detail in stages:
        rendered = ", ".join(f"{k}={v}" for k, v in detail.items())
        lines.append(f"  {name:<6} {rendered}")
    return "\n".join(lines)


def failure_banner(stage: str, error: str) -> str:
    """Unmissable, never a silent partial sync (T9 ruling)."""
    bar = "#" * 64
    return (
        f"{bar}\n"
        f"## SYNC FAILED at stage '{stage}' — PARTIAL SYNC, DO NOT TRUST\n"
        f"## corpus/ and the DB may now disagree; re-run after fixing.\n"
        f"## cause: {error}\n"
        f"{bar}"
    )


# ---------- orchestration (live path; exercised post-dispatch) ----------

def _read_db_pins(db_url: str) -> dict[str, str] | None:
    import psycopg

    with psycopg.connect(db_url) as conn:
        if conn.execute("SELECT to_regclass('ingest_meta')").fetchone()[0] is None:
            return None
        return dict(conn.execute("SELECT key, value FROM ingest_meta").fetchall())


def _trace(langfuse, status: str, stages: list[tuple[str, dict]],
           error: str | None = None) -> None:
    langfuse.trace(
        name="sync",
        input={"corpus_dir": str(CORPUS_DIR)},
        output={"status": status, "stages": dict(stages), "error": error,
                "summary": format_summary(stages)},
    )
    langfuse.flush()


def profile_refusal(profile_name: str) -> str | None:
    """P5-T2: sync is the PERSONAL pipeline — it pulls the owner's Neon EM into
    corpus/ and ingests it. It has no meaning under another profile, and
    running it while the demo profile is active is the precise confusion
    app/profile.py exists to prevent: an operator who believes they are
    driving the demo, moving personal documents. Refuse rather than surprise;
    the profile is a one-line edit away if the operator meant it."""
    if profile_name == "personal":
        return None
    return (f"REFUSING TO SYNC: active corpus profile is {profile_name!r}. "
            "sync exports the owner's PERSONAL corpus from Neon into corpus/ "
            "— it is not the demo pipeline (that is "
            "scripts/export_demo_corpus.py). Set config/corpus.json's "
            "\"profile\" to \"personal\" if this is what you meant.")


def main() -> int:
    from langfuse import Langfuse
    from openai import OpenAI

    refusal = profile_refusal(load_profile().name)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print(f"REFUSING TO SYNC: missing env {missing} "
              "(set -a; source .env; set +a)", file=sys.stderr)
        return 2

    # Pre-flight refuse-to-mix check — BEFORE any stage touches anything.
    refusal = pin_refusal(_read_db_pins(os.environ["APP_DATABASE_URL"]))
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    langfuse = Langfuse()  # reads LANGFUSE_* from env
    stages: list[tuple[str, dict]] = []
    stage = "export"
    try:
        exported = run_export(os.environ["APP_CORPUS_SOURCE_URL"])
        stages.append(("export", {
            **{t: n for t, n in exported.exported.items()},
            "total": exported.total,
            "skipped_empty": sum(exported.skipped.values()),
        }))

        stage = "prune"  # runs only on a COMPLETE export set
        disk = {f.name for f in CORPUS_DIR.glob("*.md")}
        pruned = compute_prune_set(disk, exported.filenames)
        for name in pruned:
            (CORPUS_DIR / name).unlink()
        stages.append(("prune", {
            "pruned": len(pruned),
            "files": pruned[:10] + (["..."] if len(pruned) > 10 else []),
        }))

        stage = "ingest"
        client = OpenAI(
            base_url=os.environ.get("GATEWAY", "http://localhost:4000"),
            api_key="anything")
        ingested = run_ingest(CORPUS_DIR, os.environ["APP_DATABASE_URL"], client)
        stages.append(("ingest", {
            "embedded": ingested.embedded, "unchanged": ingested.skipped,
            "deleted": ingested.deleted,
            "chunks_written": ingested.chunks_written,
            "chunks_total": ingested.total_chunks,
            "elapsed_s": round(ingested.elapsed, 1),
        }))
    except (Exception, SystemExit) as exc:  # SystemExit: check_meta refuses via it
        print(failure_banner(stage, f"{type(exc).__name__}: {exc}"), file=sys.stderr)
        try:
            _trace(langfuse, f"failed:{stage}", stages, error=str(exc))
        except Exception as trace_exc:
            print(f"(sync failure additionally not traced: {trace_exc})",
                  file=sys.stderr)
        return 1

    print(format_summary(stages))
    try:
        _trace(langfuse, "ok", stages)
    except Exception as exc:
        # Data stages succeeded but the run is invisible to observability —
        # still red (T9: EVERY run logs a sync summary trace).
        print(failure_banner("trace", f"sync completed but Langfuse trace "
                             f"failed: {exc}"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
