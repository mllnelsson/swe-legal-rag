---
type: API Endpoint
title: Document PDF Endpoint (GET /api/documents/{id}/pdf)
description: The GET /api/documents/{id}/pdf contract — the original PDF streamed inline as application/pdf, proxied through the API rather than a signed storage URL.
resource: GET /api/documents/{document_id}/pdf
tags: [api, documents, rest, pdf]
timestamp: 2026-08-03T00:00:00Z
---

# Document PDF Endpoint (`GET /api/documents/{document_id}/pdf`)

Streams a decision's original PDF, `Content-Type: application/pdf`,
`Content-Disposition: inline` so a browser (or an `<embed>`) renders it in place rather
than downloading it.

404s when the document is unknown or has no stored PDF.

## Why proxied, not a signed URL

`LocalStorageBackend.get_url` returns an absolute filesystem path, which no browser can
open, so the endpoint reads the bytes via `storage.retrieve()` and streams them itself.
This keeps one URL shape (`GET /api/documents/{id}/pdf`) across the local and GCS storage
backends, rather than the client branching on which one is deployed.

The storage key is `shared.storage.keys.document_pdf_key(document_id)` —
`documents/{id}/original.pdf` — the same helper the [download](/pipeline/download.md) and
[parse](/pipeline/parse.md) workers use to write and read it, and that the [chat
endpoint](/api/chat-endpoint.md)'s `pdf_url` resolves through `storage.get_url()` for. It
is a shared contract, not any one caller's private detail — see [shared](/packages/shared.md).

A stored `gcs_uri` with no bytes at that key means storage and the database have
diverged; the endpoint logs a warning and returns 404 rather than a 500.

Implemented by `api/services/document_service.get_document_pdf`, served through the [api
package](/packages/api.md).
