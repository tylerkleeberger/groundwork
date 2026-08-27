---
source_id: "8828ec6b-c942-519b-8190-cb7f087cdc7d"
title: "Status Codes"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "reference"
layer: "reference"
upstream_path: "reference/status.md"
---

# Status Codes

You can import the `status` module from `fastapi`:

```python
from fastapi import status
```

`status` is provided directly by Starlette.

It contains a group of named constants (variables) with integer status codes.

For example:

* 200: `status.HTTP_200_OK`
* 403: `status.HTTP_403_FORBIDDEN`
* etc.

It can be convenient to quickly access HTTP (and WebSocket) status codes in your app, using autocompletion for the name without having to memorize the integer status codes.

Read more about it in the [FastAPI docs about Response Status Code](https://fastapi.tiangolo.com/tutorial/response-status-code/).

## Example

```python
from fastapi import FastAPI, status

app = FastAPI()


@app.get("/items/", status_code=status.HTTP_418_IM_A_TEAPOT)
def read_items():
    return [{"name": "Plumbus"}, {"name": "Portal Gun"}]
```

::: fastapi.status
