---
source_id: "c2a331eb-7ab2-5856-8fd1-660ea3865cd5"
title: "Test Client - `TestClient`"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "reference"
layer: "reference"
upstream_path: "reference/testclient.md"
---

# Test Client - `TestClient`

You can use the `TestClient` class to test FastAPI applications without creating an actual HTTP and socket connection, just communicating directly with the FastAPI code.

Read more about it in the [FastAPI docs for Testing](https://fastapi.tiangolo.com/tutorial/testing/).

You can import it directly from `fastapi.testclient`:

```python
from fastapi.testclient import TestClient
```

::: fastapi.testclient.TestClient
