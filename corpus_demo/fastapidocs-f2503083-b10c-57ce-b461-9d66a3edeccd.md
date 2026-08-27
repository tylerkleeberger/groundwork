---
source_id: "f2503083-b10c-57ce-b461-9d66a3edeccd"
title: "`Response` class"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "reference"
layer: "reference"
upstream_path: "reference/response.md"
---

# `Response` class

You can declare a parameter in a *path operation function* or dependency to be of type `Response` and then you can set data for the response like headers or cookies.

You can also use it directly to create an instance of it and return it from your *path operations*.

Read more about it in the [FastAPI docs about returning a custom Response](https://fastapi.tiangolo.com/advanced/response-directly/#returning-a-custom-response)

You can import it directly from `fastapi`:

```python
from fastapi import Response
```

::: fastapi.Response
