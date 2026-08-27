# Attribution

The documents in this directory are **not original work**. They are the
documentation of **FastAPI**, redistributed here as a public demo corpus so
that anyone can reproduce this project's published evaluation numbers against
material they can read for themselves.

| | |
|---|---|
| **Upstream project** | FastAPI |
| **Source repository** | https://github.com/fastapi/fastapi.git |
| **Release** | 0.141.1 |
| **Pinned commit** | `95f8322ee1dcda7ceace7b1c4f6c9915b36d748f` |
| **Commit date** | 2026-07-29T17:15:38+00:00 |
| **Path taken** | `docs/en/docs` |
| **Documents** | 155 |
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
