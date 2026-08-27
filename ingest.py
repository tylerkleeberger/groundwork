"""P1-T2 ingestion v1: corpus/*.md -> chunks -> embeddings -> pgvector.

Pipeline (SPEC-P1 T2): parse frontmatter + body -> structural chunking,
400-800 estimated tokens, on heading > paragraph boundaries, never
mid-sentence -> per-chunk metadata from frontmatter -> embed -> store.
Idempotent: sha256 per file; re-runs re-embed only changed files; chunks of
deleted files are removed.

Token estimate: chars/4 (deterministic, dependency-free; tiktoken's network
fetch on first use would make offline CI flaky). Chunk bounds are targets,
not laws: a section smaller than the minimum stays one faithful chunk, and
a single sentence longer than the maximum is never split.

Run: set -a; source .env; set +a; python ingest.py corpus/
Offline tests for the pure logic: tests/test_ingest.py (D16 unmarked).
"""

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from app.profile import load_profile, schema_connect_kwargs

# P5-T3: files a corpus directory carries ABOUT itself — provenance and
# licence, not documents. They live beside the corpus (the demo corpus must
# ship its upstream LICENSE and ATTRIBUTION.md), and ATTRIBUTION.md would
# otherwise be swept up by the `*.md` glob below and ingested as a document,
# silently adding a 156th "doc" that answers questions about licensing.
# One list, imported by the exporter that writes them, so writer and reader
# cannot disagree about what is metadata.
CORPUS_METADATA_FILES = frozenset({
    "ATTRIBUTION.md", "LICENSE", "LICENSE.md", "MANIFEST.json",
})

TOKEN_MIN = 400
TOKEN_MAX = 800

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


# ---------- pure logic (offline-tested) ----------

def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse the export format (scripts/export_corpus.py is the writer):
    `---` fence, `key: value` lines where strings are JSON-encoded and
    datetimes are bare ISO scalars. Returns (fields, body)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, _, raw = line.partition(": ")
        raw = raw.strip()
        if raw.startswith('"'):
            try:
                fields[key] = json.loads(raw)
            except json.JSONDecodeError:
                fields[key] = raw.strip('"')
        else:
            fields[key] = raw
    return fields, text[end + 5:].lstrip("\n")


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text) if s.strip()]


@dataclass(frozen=True)
class Chunk:
    content: str
    section: str          # nearest enclosing heading ("" before any heading)
    index: int            # position within the file
    token_estimate: int


def _flush(parts: list[str], section: str, out: list[Chunk]) -> None:
    content = "\n\n".join(parts).strip()
    if content:
        out.append(Chunk(content, section, len(out), estimate_tokens(content)))


def chunk_body(body: str) -> list[Chunk]:
    """Structural chunking. Headings are hard boundaries (heading >
    paragraph); within a section, paragraphs accumulate greedily toward
    TOKEN_MAX; an oversized paragraph falls back to sentence accumulation;
    a single oversized sentence stays whole (never mid-sentence)."""
    chunks: list[Chunk] = []
    section = ""
    parts: list[str] = []
    chars = 0  # exact chars of "\n\n".join(parts) — no estimate drift

    def emit_unit(unit: str) -> None:
        nonlocal parts, chars
        joined = chars + (2 if parts else 0) + len(unit)
        if parts and round(joined / 4) > TOKEN_MAX:
            _flush(parts, section, chunks)
            parts, chars = [], 0
            joined = len(unit)
        parts.append(unit)
        chars = joined

    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        heading = _HEADING.match(block.splitlines()[0])
        if heading and len(block.splitlines()) == 1:
            _flush(parts, section, chunks)          # heading = hard boundary
            parts, chars = [], 0
            section = heading.group(2).strip()
            continue
        if estimate_tokens(block) > TOKEN_MAX:
            for sentence in split_sentences(block):
                emit_unit(sentence)
        else:
            emit_unit(block)

    _flush(parts, section, chunks)
    return chunks


CHUNK_METADATA_KEYS = (
    "source_id", "title", "domain", "layer", "updated_at", "source_table",
)


def chunk_records(path: str, raw: bytes) -> list[dict]:
    """File bytes -> list of dicts ready for the store step: chunk fields +
    the frontmatter metadata carried per chunk (SPEC-P1 T2)."""
    fields, body = parse_frontmatter(raw.decode("utf-8"))
    meta = {k: fields.get(k, "") for k in CHUNK_METADATA_KEYS}
    return [
        {
            "file_path": path,
            "chunk_index": c.index,
            "section": c.section,
            "content": c.content,
            "token_estimate": c.token_estimate,
            **meta,
        }
        for c in chunk_body(body)
    ]


# ---------- embed + store (owner-approved 2026-07-06; D17) ----------

EMBED_ALIAS = "embed"                 # gateway alias -> ollama/nomic-embed-text
EMBED_MODEL_ID = "nomic-embed-text"   # pinned identity, recorded in ingest_meta
EMBED_DIMS = 768
DOC_PREFIX = "search_document: "      # nomic task prefix, corpus side
QUERY_PREFIX = "search_query: "       # T3 retrieval MUST use this on queries —
                                      # mixing prefixes silently degrades recall
EMBED_BATCH = 64

DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS files (
  path          text PRIMARY KEY,
  content_hash  text NOT NULL,
  source_id     text NOT NULL,
  embedded_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chunks (
  id             bigserial PRIMARY KEY,
  file_path      text NOT NULL REFERENCES files(path) ON DELETE CASCADE,
  chunk_index    int  NOT NULL,
  section        text NOT NULL DEFAULT '',
  content        text NOT NULL,
  token_estimate int  NOT NULL,
  source_id      text NOT NULL,
  title          text,
  domain         text,
  layer          text,
  updated_at     timestamptz,
  source_table   text,
  embedding      vector({EMBED_DIMS}) NOT NULL,
  UNIQUE (file_path, chunk_index)
);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops);
-- P1-T7 hybrid retrieval: FTS column, additive + no data risk (generated
-- column stays in sync with content by construction; ALTER ... IF NOT EXISTS
-- keeps the DDL-in-code approach idempotent). Migration tooling still
-- deferred per the T2 ruling — this is not a data-risking change.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);
CREATE TABLE IF NOT EXISTS ingest_meta (
  key text PRIMARY KEY,
  value text NOT NULL
);
"""


def embed_texts(client, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        resp = client.embeddings.create(
            model=EMBED_ALIAS,
            input=[DOC_PREFIX + t for t in texts[i:i + EMBED_BATCH]],
        )  # gateway drops encoding_format for ollama (drop_params on the alias)
        out.extend(d.embedding for d in resp.data)
    return out


def check_meta(conn) -> None:
    """Pin enforcement: refuse to mix embeddings from different models."""
    rows = dict(conn.execute("SELECT key, value FROM ingest_meta").fetchall())
    want = {"embedding_model": EMBED_MODEL_ID, "dimensions": str(EMBED_DIMS)}
    if not rows:
        for k, v in want.items():
            conn.execute("INSERT INTO ingest_meta VALUES (%s, %s)", (k, v))
        return
    if rows != want:
        raise SystemExit(
            f"REFUSING to mix embedding models: DB has {rows}, code wants {want}.\n"
            f"Changing models requires a deliberate full re-embed (D17)."
        )


@dataclass
class IngestResult:
    """Per-run counts, returned so scripts/sync.py (P1-T9) can assemble its
    per-stage summary without re-parsing printed output."""
    embedded: int
    skipped: int
    deleted: int
    chunks_written: int
    total_chunks: int
    elapsed: float


def run_ingest(corpus: Path, db_url: str, client, schema: str = "public") -> IngestResult:
    import time

    import psycopg

    start = time.monotonic()
    disk = {f.name: f.read_bytes() for f in sorted(corpus.glob("*.md"))
            if f.name not in CORPUS_METADATA_FILES}
    hashes = {name: file_hash(data) for name, data in disk.items()}

    embedded = skipped = deleted = chunks_written = 0
    # The profile's schema is created and put FIRST on the search_path, so the
    # unqualified DDL and every statement below land in it. Two corpora can
    # therefore share one database without sharing one `chunks` table — which
    # is what makes the demo profile safe to run beside the personal one.
    with psycopg.connect(db_url, **schema_connect_kwargs(schema)) as conn:
        if schema != "public":
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        conn.execute(DDL)
        check_meta(conn)
        known = dict(conn.execute("SELECT path, content_hash FROM files").fetchall())

        for name in sorted(set(known) - set(disk)):
            conn.execute("DELETE FROM files WHERE path = %s", (name,))  # chunks cascade
            deleted += 1

        for name, data in disk.items():
            if known.get(name) == hashes[name]:
                skipped += 1
                continue
            records = chunk_records(name, data)
            vectors = embed_texts(client, [r["content"] for r in records])
            with conn.transaction():
                conn.execute("DELETE FROM files WHERE path = %s", (name,))
                conn.execute(
                    "INSERT INTO files (path, content_hash, source_id) VALUES (%s,%s,%s)",
                    (name, hashes[name], records[0]["source_id"] if records else ""),
                )
                for r, v in zip(records, vectors, strict=True):
                    conn.execute(
                        """INSERT INTO chunks (file_path, chunk_index, section,
                             content, token_estimate, source_id, title, domain,
                             layer, updated_at, source_table, embedding)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)""",
                        (r["file_path"], r["chunk_index"], r["section"],
                         r["content"], r["token_estimate"], r["source_id"],
                         r["title"], r["domain"], r["layer"],
                         r["updated_at"] or None, r["source_table"], str(v)),
                    )
                chunks_written += len(records)
            embedded += 1

        total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    return IngestResult(embedded, skipped, deleted, chunks_written, total,
                        time.monotonic() - start)


def main() -> int:
    from openai import OpenAI

    # D7's profile decides WHICH corpus and WHERE it lands; an explicit argv
    # path still wins, so existing invocations are unchanged.
    prof = load_profile()
    corpus = Path(sys.argv[1]) if len(sys.argv) > 1 else prof.corpus_dir
    if not corpus.is_dir():
        print(f"ERROR: corpus dir not found: {corpus}", file=sys.stderr)
        return 1
    db_url = os.environ.get("APP_DATABASE_URL")
    if not db_url:
        print("ERROR: APP_DATABASE_URL not set (set -a; source .env; set +a)",
              file=sys.stderr)
        return 1
    client = OpenAI(base_url=os.environ.get("GATEWAY", "http://localhost:4000"),
                    api_key="anything")

    print(f"profile: {prof.name} | corpus: {corpus} | schema: {prof.db_schema}")
    r = run_ingest(corpus, db_url, client, schema=prof.db_schema)
    print(f"files: {r.embedded} embedded, {r.skipped} unchanged, {r.deleted} deleted")
    print(f"chunks in DB: {r.total_chunks} | written this run: {r.chunks_written}")
    print(f"elapsed: {r.elapsed:.1f}s"
          + (f" ({r.chunks_written / r.elapsed:.0f} chunks/s)" if r.chunks_written else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
