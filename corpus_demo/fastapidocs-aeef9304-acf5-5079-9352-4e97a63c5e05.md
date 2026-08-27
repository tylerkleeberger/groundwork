---
source_id: "aeef9304-acf5-5079-9352-4e97a63c5e05"
title: "`UploadFile` class"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "reference"
layer: "reference"
upstream_path: "reference/uploadfile.md"
---

# `UploadFile` class

You can define *path operation function* parameters to be of the type `UploadFile` to receive files from the request.

You can import it directly from `fastapi`:

```python
from fastapi import UploadFile
```

::: fastapi.UploadFile
    options:
        members:
            - file
            - filename
            - size
            - headers
            - content_type
            - read
            - write
            - seek
            - close
