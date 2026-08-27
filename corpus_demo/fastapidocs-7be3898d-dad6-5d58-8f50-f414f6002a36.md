---
source_id: "7be3898d-dad6-5d58-8f50-f414f6002a36"
title: "JSON with Bytes as Base64"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "advanced"
layer: "reference"
upstream_path: "advanced/json-base64-bytes.md"
---

# JSON with Bytes as Base64 { #json-with-bytes-as-base64 }

If your app needs to receive and send JSON data, but you need to include binary data in it, you can encode it as base64.

## Base64 vs Files { #base64-vs-files }

Consider first if you can use [Request Files](../tutorial/request-files.md) for uploading binary data and [Custom Response - FileResponse](./custom-response.md#fileresponse) for sending binary data, instead of encoding it in JSON.

JSON can only contain UTF-8 encoded strings, so it can't contain raw bytes.

Base64 can encode binary data in strings, but to do it, it needs to use more characters than the original binary data, so it would normally be less efficient than regular files.

Use base64 only if you definitely need to include binary data in JSON, and you can't use files for that.

## Pydantic `bytes` { #pydantic-bytes }

You can declare a Pydantic model with `bytes` fields, and then use `val_json_bytes` in the model config to tell it to use base64 to *validate* input JSON data, as part of that validation it will decode the base64 string into bytes.



If you check the `/docs`, they will show that the field `data` expects base64 encoded bytes:

<div class="screenshot">
<img src="/img/tutorial/json-base64-bytes/image01.png">
</div>

You could send a request like:

```json
{
    "description": "Some data",
    "data": "aGVsbG8="
}
```

/// tip

`aGVsbG8=` is the base64 encoding of `hello`.

///

And then Pydantic will decode the base64 string and give you the original bytes in the `data` field of the model.

You will receive a response like:

```json
{
  "description": "Some data",
  "content": "hello"
}
```

## Pydantic `bytes` for Output Data { #pydantic-bytes-for-output-data }

You can also use `bytes` fields with `ser_json_bytes` in the model config for output data, and Pydantic will *serialize* the bytes as base64 when generating the JSON response.



## Pydantic `bytes` for Input and Output Data { #pydantic-bytes-for-input-and-output-data }

And of course, you can use the same model configured to use base64 to handle both input (*validate*) with `val_json_bytes` and output (*serialize*) with `ser_json_bytes` when receiving and sending JSON data.
