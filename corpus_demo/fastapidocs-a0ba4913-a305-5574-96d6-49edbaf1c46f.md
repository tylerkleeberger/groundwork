---
source_id: "a0ba4913-a305-5574-96d6-49edbaf1c46f"
title: "Testing Events: lifespan and startup - shutdown"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "advanced"
layer: "reference"
upstream_path: "advanced/testing-events.md"
---

# Testing Events: lifespan and startup - shutdown { #testing-events-lifespan-and-startup-shutdown }

When you need `lifespan` to run in your tests, you can use the `TestClient` with a `with` statement:




You can read more details about the ["Running lifespan in tests in the official Starlette documentation site."](https://starlette.dev/lifespan/#running-lifespan-in-tests)

For the deprecated `startup` and `shutdown` events, you can use the `TestClient` as follows:
