"""P5-T2 demo corpus export: FastAPI documentation -> corpus_demo/*.md

WHY A PIN. The published README numbers must be reproducible by a stranger.
A moving corpus makes them irreproducible — the same eval run against a
different upstream HEAD is a different measurement wearing the same number.
So the source is pinned to ONE commit, recorded here, in the journal, and in
the exported manifest.

WHY REUSE, NOT REIMPLEMENT. The front-matter shape is not copied from
scripts/export_corpus.py — this module IMPORTS its writers (`filename_for`,
`yaml_scalar`, `frontmatter`, `document`). Ingestion, retrieval and evals are
therefore untouched by construction rather than by inspection: if the personal
exporter's shape ever changes, this one changes with it or fails loudly.

DETERMINISM. Nothing here reads the clock. `updated_at` is the PINNED COMMIT's
authored date, not "now", so re-running the exporter produces byte-identical
files — which is what makes the demo corpus a fixture rather than a snapshot.

Run: python scripts/export_demo_corpus.py [--out corpus_demo] [--keep-clone]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_corpus import document, filename_for  # noqa: E402  (shared writer)

# ── the pin ────────────────────────────────────────────────────────────────
# FastAPI 0.141.1. Recorded as tag + sha: the tag is what a reader recognises,
# the sha is what actually reproduces (a tag can be moved; a sha cannot).
UPSTREAM_REPO = "https://github.com/fastapi/fastapi.git"
PINNED_TAG = "0.141.1"
PINNED_COMMIT = "95f8322ee1dcda7ceace7b1c4f6c9915b36d748f"
DOCS_SUBDIR = "docs/en/docs"

SOURCE_TABLE = "FastapiDocs"
# A fixed namespace makes source_ids stable across machines and runs: the same
# document path always yields the same id, so re-export overwrites in place and
# citations stay valid — the same property `filename_for` relies on.
ID_NAMESPACE = uuid.UUID("6f9f2f2e-6b1e-5f5b-9d3a-7c2f4c9a8e10")

REPO_ROOT = Path(__file__).resolve().parent.parent


def source_id_for(rel_path: str) -> str:
    """Deterministic, UUID-shaped id derived from the document's path."""
    return str(uuid.uuid5(ID_NAMESPACE, rel_path))


_ANCHOR = re.compile(r"\s*\{\s*#[^}]*\}\s*$")


def title_for(body: str, rel_path: str) -> str:
    """The document's first H1, else a readable fallback from the path.

    FastAPI's headings carry an explicit anchor suffix (`{ #some-anchor }`).
    It is markup, not title text, and titles are what a citation shows the
    reader — so it is stripped here rather than surfacing in every citation.
    """
    for line in body.splitlines():
        if line.startswith("# "):
            return _ANCHOR.sub("", line[2:]).strip()
    return Path(rel_path).stem.replace("-", " ").replace("_", " ").title()


def domain_for(rel_path: str) -> str:
    """Top-level docs section ('tutorial', 'advanced', …) as the domain
    enrichment. Root-level pages carry 'guide' rather than an empty string so
    the field is always meaningful."""
    parts = Path(rel_path).parts
    return parts[0] if len(parts) > 1 else "guide"


def strip_mkdocs_macros(text: str) -> str:
    """FastAPI's docs embed mkdocs-macros blocks (`{* … *}`) that reference
    example files by path. They carry no prose, and left in place they become
    chunk content that reads as noise to a retriever. Removed; everything else
    is kept verbatim."""
    out, depth = [], 0
    i = 0
    while i < len(text):
        if text.startswith("{*", i):
            depth += 1
            i += 2
            continue
        if text.startswith("*}", i) and depth:
            depth -= 1
            i += 2
            continue
        if not depth:
            out.append(text[i])
        i += 1
    return "".join(out)


def to_corpus_file(rel_path: str, raw: str, commit_date: str) -> tuple[str, str]:
    """One upstream doc -> (filename, file content) in the existing shape."""
    body = strip_mkdocs_macros(raw).strip()
    source_id = source_id_for(rel_path)
    fields = {
        "source_id": source_id,
        "title": title_for(body, rel_path),
        "updated_at": commit_date,
        "source_table": SOURCE_TABLE,
        "kb_type": "DOC",
        "status": "PUBLISHED",
        "domain": domain_for(rel_path),
        "layer": "reference",
        "upstream_path": rel_path,
    }
    return filename_for(SOURCE_TABLE, source_id), document(fields, body + "\n")


def fetch_docs(workdir: Path) -> tuple[Path, str]:
    """Fetch ONLY the pinned commit, sparsely, and return (docs dir, date).

    `git fetch --depth 1 <sha>` fetches exactly the pin — not a branch that
    could have moved between the pin being written and this run.
    """
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(workdir), *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    workdir.mkdir(parents=True, exist_ok=True)
    git("init", "-q")
    git("remote", "add", "origin", UPSTREAM_REPO)
    git("sparse-checkout", "set", "--cone", DOCS_SUBDIR)
    git("fetch", "-q", "--depth", "1", "origin", PINNED_COMMIT)
    git("checkout", "-q", "FETCH_HEAD")

    landed = git("rev-parse", "HEAD")
    if landed != PINNED_COMMIT:
        raise SystemExit(
            f"REFUSING: checked out {landed}, expected the pin {PINNED_COMMIT}. "
            "An unpinned corpus makes published numbers irreproducible."
        )
    commit_date = git("show", "-s", "--format=%cI", "HEAD")
    return workdir / DOCS_SUBDIR, commit_date


def export(out_dir: Path, workdir: Path) -> dict:
    docs_dir, commit_date = fetch_docs(workdir)
    if not docs_dir.is_dir():
        raise SystemExit(f"REFUSING: docs path absent at the pin: {DOCS_SUBDIR}")

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.md"):
        stale.unlink()

    written = 0
    for path in sorted(docs_dir.rglob("*.md")):
        rel = path.relative_to(docs_dir).as_posix()
        raw = path.read_text(encoding="utf-8", errors="replace")
        name, content = to_corpus_file(rel, raw, commit_date)
        (out_dir / name).write_text(content, encoding="utf-8")
        written += 1

    manifest = {
        "upstream_repo": UPSTREAM_REPO,
        "pinned_tag": PINNED_TAG,
        "pinned_commit": PINNED_COMMIT,
        "commit_date": commit_date,
        "docs_subdir": DOCS_SUBDIR,
        "source_table": SOURCE_TABLE,
        "documents": written,
    }
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_attribution(out_dir, workdir, commit_date, written)
    return manifest


ATTRIBUTION_TEMPLATE = """\
# Attribution

The documents in this directory are **not original work**. They are the
documentation of **FastAPI**, redistributed here as a public demo corpus so
that anyone can reproduce this project's published evaluation numbers against
material they can read for themselves.

| | |
|---|---|
| **Upstream project** | FastAPI |
| **Source repository** | {repo} |
| **Release** | {tag} |
| **Pinned commit** | `{sha}` |
| **Commit date** | {date} |
| **Path taken** | `{subdir}` |
| **Documents** | {count} |
| **Licence** | MIT — see `LICENSE` in this directory, copied verbatim from the pinned commit |

The corpus is pinned to that exact commit. A moving corpus would make the
published numbers irreproducible: the same evaluation run against a different
upstream HEAD is a different measurement wearing the same number.

Each document is the upstream markdown with front matter added
(`source_id`/`title`/`source_table`/`upstream_path`) so it enters this
project's ingestion pipeline in the same shape as any other corpus document.
`upstream_path` in each file names the original, so every document here can be
traced back to its source in the upstream repository.

Regenerate with `python scripts/export_demo_corpus.py`. This file and
`LICENSE` are rewritten by that script on every run, so they cannot drift
away from the pin they describe.
"""


def write_attribution(out_dir: Path, workdir: Path, commit_date: str,
                      written: int) -> None:
    """Write LICENSE + ATTRIBUTION.md ON EVERY RUN (director ruling,
    2026-08-26, due before the public flip).

    Both are DERIVED from the pin rather than maintained beside it — the same
    reason `updated_at` is the commit's date and not the clock. A licence file
    that has to be remembered is a licence file that goes stale the first time
    the pin moves, and stale attribution on redistributed third-party work is
    the kind of error that is embarrassing in exactly the public setting this
    corpus exists for.
    """
    upstream_license = workdir / "LICENSE"
    if not upstream_license.is_file():
        raise SystemExit(
            "REFUSING: upstream LICENSE not present at the pin — the demo "
            "corpus redistributes third-party documents and must carry their "
            "licence. Not shipping it is not an option; shipping a guess is "
            "worse."
        )
    (out_dir / "LICENSE").write_text(
        upstream_license.read_text(encoding="utf-8"), encoding="utf-8")
    (out_dir / "ATTRIBUTION.md").write_text(
        ATTRIBUTION_TEMPLATE.format(
            repo=UPSTREAM_REPO, tag=PINNED_TAG, sha=PINNED_COMMIT,
            date=commit_date, subdir=DOCS_SUBDIR, count=written),
        encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO_ROOT / "corpus_demo"))
    ap.add_argument("--keep-clone", action="store_true")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="fastapi-docs-pin-"))
    try:
        manifest = export(Path(args.out), tmp)
    finally:
        if not args.keep_clone:
            subprocess.run(["rm", "-rf", str(tmp)], check=False)

    print(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\n{manifest['documents']} documents -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
