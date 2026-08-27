---
source_id: "7555dbf8-d63f-567a-a6f5-09b9be816bae"
title: "Server-Sent Events - `EventSourceResponse` and `ServerSentEvent`"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "reference"
layer: "reference"
upstream_path: "reference/sse.md"
---

# Server-Sent Events - `EventSourceResponse` and `ServerSentEvent`

To stream Server-Sent Events (SSE), use `yield` in your *path operation function* and set `response_class=EventSourceResponse`.

If you need to set SSE fields like `event`, `id`, `retry`, or `comment`, you can `yield` `ServerSentEvent` objects instead of plain data.

Read more about it in the [FastAPI docs for Server-Sent Events (SSE)](https://fastapi.tiangolo.com/tutorial/server-sent-events/).

You can import them directly from `fastapi.sse`:

```python
from fastapi.sse import EventSourceResponse, ServerSentEvent
```

::: fastapi.sse.EventSourceResponse

::: fastapi.sse.ServerSentEvent
