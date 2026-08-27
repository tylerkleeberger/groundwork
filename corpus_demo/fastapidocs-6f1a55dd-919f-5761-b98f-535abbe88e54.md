---
source_id: "6f1a55dd-919f-5761-b98f-535abbe88e54"
title: "Exceptions - `HTTPException` and `WebSocketException`"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "reference"
layer: "reference"
upstream_path: "reference/exceptions.md"
---

# Exceptions - `HTTPException` and `WebSocketException`

These are the exceptions that you can raise to show errors to the client.

When you raise an exception, as would happen with normal Python, the rest of the execution is aborted. This way you can raise these exceptions from anywhere in the code to abort a request and show the error to the client.

You can use:

* `HTTPException`
* `WebSocketException`

These exceptions can be imported directly from `fastapi`:

```python
from fastapi import HTTPException, WebSocketException
```

::: fastapi.HTTPException

::: fastapi.WebSocketException
