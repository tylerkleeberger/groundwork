"""P5-T2 ingestion parity capture: prove the profile seam changed NOTHING.

The claim under test is narrow and checkable: for the PERSONAL profile,
ingestion behaves byte-identically before and after the profile wiring — same
chunking, same embed path, same store contract. The run_ask precedent: an
additive refactor is proven by holding the observable output byte-identical,
not by reading the diff and agreeing with it.

WHAT IS CAPTURED, and why each piece:
  * per file: name, content hash, chunk count, and per chunk the section,
    index, token estimate and a sha256 of the chunk content — this is CHUNKING,
    the part of ingestion that decides what a retriever can ever see;
  * the embed path's identity: model, dimensions and the document-side task
    prefix — an embedding produced under a different prefix is a different
    vector space, and that failure is invisible in any row count;
  * the store contract: a hash of the DDL and of the INSERT column list — the
    shape the chunks land in.

No database and no network: chunking is pure, and the identity pieces are read
from the module. That is what makes this runnable on both sides of a change.

Run: .venv/bin/python scripts/ingest_parity.py [--corpus corpus] [--out FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ingest  # noqa: E402


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def capture(corpus: Path) -> dict:
    files = []
    for path in sorted(corpus.glob("*.md")):
        raw = path.read_text()
        fields, body = ingest.parse_frontmatter(raw)
        chunks = ingest.chunk_body(body)
        files.append({
            "name": path.name,
            "content_sha256": ingest.file_hash(path.read_bytes()),
            "frontmatter_keys": sorted(fields),
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "index": c.index,
                    "section": c.section,
                    "token_estimate": c.token_estimate,
                    "content_sha256": sha(c.content),
                }
                for c in chunks
            ],
        })

    # The store contract, read from the module rather than restated here.
    insert_cols = re.search(r"INSERT INTO chunks\s*\(([^)]*)\)",
                            Path(ingest.__file__).read_text(), re.S)
    return {
        "corpus_dir": corpus.name,
        "file_count": len(files),
        "total_chunks": sum(f["chunk_count"] for f in files),
        "embed_path": {
            "model": ingest.EMBED_MODEL_ID,
            "dims": ingest.EMBED_DIMS,
            "doc_prefix": ingest.DOC_PREFIX,
            "batch": ingest.EMBED_BATCH,
        },
        "chunking": {"token_max": ingest.TOKEN_MAX},
        "store_contract": {
            "ddl_sha256": sha(ingest.DDL),
            "insert_columns_sha256": sha(" ".join(insert_cols.group(1).split()))
            if insert_cols else None,
        },
        "files": files,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--out")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        print(f"REFUSING: corpus dir not found: {corpus}", file=sys.stderr)
        return 2
    snapshot = capture(corpus)
    if snapshot["file_count"] == 0:
        # An empty capture would compare equal to any other empty capture: the
        # same unearned-verdict shape the leak scanner refuses on empty seeds.
        print("REFUSING: zero files captured — an empty parity snapshot "
              "would compare equal to anything", file=sys.stderr)
        return 2

    text = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text)
        print(f"{snapshot['file_count']} files, {snapshot['total_chunks']} chunks "
              f"-> {args.out}")
        print(f"digest: {sha(text)[:16]}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
