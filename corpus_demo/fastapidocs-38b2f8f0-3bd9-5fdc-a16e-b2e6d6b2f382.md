---
source_id: "38b2f8f0-3bd9-5fdc-a16e-b2e6d6b2f382"
title: "Request Forms and Files"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "tutorial"
layer: "reference"
upstream_path: "tutorial/request-forms-and-files.md"
---

# Request Forms and Files { #request-forms-and-files }

You can define files and form fields at the same time using `File` and `Form`.

/// note

To receive uploaded files and/or form data, first install [`python-multipart`](https://github.com/Kludex/python-multipart).

Add it to your project:

```console
$ uv add python-multipart
```

///

## Import `File` and `Form` { #import-file-and-form }



## Define `File` and `Form` parameters { #define-file-and-form-parameters }

Create file and form parameters the same way you would for `Body` or `Query`:



The files and form fields will be uploaded as form data and you will receive the files and form fields.

And you can declare some of the files as `bytes` and some as `UploadFile`.

/// warning

You can declare multiple `File` and `Form` parameters in a *path operation*, but you can't also declare `Body` fields that you expect to receive as JSON, as the request will have the body encoded using `multipart/form-data` instead of `application/json`.

This is not a limitation of **FastAPI**, it's part of the HTTP protocol.

///

## Recap { #recap }

Use `File` and `Form` together when you need to receive data and files in the same request.
