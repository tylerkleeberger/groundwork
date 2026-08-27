---
source_id: "8a379af4-50a0-5ecc-8d1b-20e7c384b91d"
title: "`HTTPConnection` class"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "reference"
layer: "reference"
upstream_path: "reference/httpconnection.md"
---

# `HTTPConnection` class

When you want to define dependencies that should be compatible with both HTTP and WebSockets, you can define a parameter that takes an `HTTPConnection` instead of a `Request` or a `WebSocket`.

You can import it from `fastapi.requests`:

```python
from fastapi.requests import HTTPConnection
```

::: fastapi.requests.HTTPConnection
