---
source_id: "e7b1677d-8da1-57ca-8ba9-a46de5167e80"
title: "Request Parameters"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "reference"
layer: "reference"
upstream_path: "reference/parameters.md"
---

# Request Parameters

Here's the reference information for the request parameters.

These are the special functions that you can put in *path operation function* parameters or dependency functions with `Annotated` to get data from the request.

It includes:

* `Query()`
* `Path()`
* `Body()`
* `Cookie()`
* `Header()`
* `Form()`
* `File()`

You can import them all directly from `fastapi`:

```python
from fastapi import Body, Cookie, File, Form, Header, Path, Query
```

::: fastapi.Query

::: fastapi.Path

::: fastapi.Body

::: fastapi.Cookie

::: fastapi.Header

::: fastapi.Form

::: fastapi.File
