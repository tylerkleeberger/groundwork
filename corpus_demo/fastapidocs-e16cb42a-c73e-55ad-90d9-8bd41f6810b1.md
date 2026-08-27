---
source_id: "e16cb42a-c73e-55ad-90d9-8bd41f6810b1"
title: "Use Old 403 Authentication Error Status Codes"
updated_at: "2026-07-29T17:15:38+00:00"
source_table: "FastapiDocs"
kb_type: "DOC"
status: "PUBLISHED"
domain: "how-to"
layer: "reference"
upstream_path: "how-to/authentication-error-status-code.md"
---

# Use Old 403 Authentication Error Status Codes { #use-old-403-authentication-error-status-codes }

Before FastAPI version `0.122.0`, when the integrated security utilities returned an error to the client after a failed authentication, they used the HTTP status code `403 Forbidden`.

Starting with FastAPI version `0.122.0`, they use the more appropriate HTTP status code `401 Unauthorized`, and return a sensible `WWW-Authenticate` header in the response, following the HTTP specifications, [RFC 7235](https://datatracker.ietf.org/doc/html/rfc7235#section-3.1), [RFC 9110](https://datatracker.ietf.org/doc/html/rfc9110#name-401-unauthorized).

But if for some reason your clients depend on the old behavior, you can revert to it by overriding the method `make_not_authenticated_error` in your security classes.

For example, you can create a subclass of `HTTPBearer` that returns a `403 Forbidden` error instead of the default `401 Unauthorized` error:



/// tip

Notice that the function returns the exception instance, it doesn't raise it. The raising is done in the rest of the internal code.

///
