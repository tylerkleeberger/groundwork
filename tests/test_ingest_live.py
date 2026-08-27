"""Live checks for the ingested corpus (D16: marked live — needs the app
Postgres; run locally, excluded from CI's offline floor)."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytestmark = pytest.mark.live


def test_ingested_corpus_state():
    import psycopg

    from ingest import EMBED_DIMS, EMBED_MODEL_ID

    url = os.environ.get("APP_DATABASE_URL")
    if not url:
        pytest.skip("APP_DATABASE_URL not set")
    with psycopg.connect(url) as conn:
        meta = dict(conn.execute("SELECT key, value FROM ingest_meta").fetchall())
        assert meta["embedding_model"] == EMBED_MODEL_ID
        assert meta["dimensions"] == str(EMBED_DIMS)
        files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert files > 0 and chunks > files  # multiple chunks per file overall
        dims = conn.execute(
            "SELECT vector_dims(embedding) FROM chunks LIMIT 1"
        ).fetchone()[0]
        assert dims == EMBED_DIMS
