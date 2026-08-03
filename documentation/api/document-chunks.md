---
type: API Endpoint
title: Document Chunks Endpoint (GET /api/documents/{id}/chunks)
description: The GET /api/documents/{id}/chunks contract — a decision's full text in reading order, chunk by chunk, optionally scoped to one section.
resource: GET /api/documents/{document_id}/chunks
tags: [api, documents, rest, chunks]
timestamp: 2026-08-03T00:00:00Z
---

# Document Chunks Endpoint (`GET /api/documents/{document_id}/chunks`)

The decision's text in the order the [chunk worker](/pipeline/chunk.md) produced it —
unlike [`/api/search`](/api/search.md), this returns everything, not a ranked subset.

An optional `section` query parameter (`body` | `appendix`) restricts to one part;
omitted, it returns both, in storage order.

404s when `document_id` is unknown.

## Response

```json
[
  {
    "chunk_id": "uuid",
    "chunk_index": 0,
    "text": "string",
    "section": "body | appendix",
    "appendix_label": "string | null"
  }
]
```

Projected from [`ChunkRead`](/data-model/chunks.md) with the embedding vector and the
contextual (summary-prepended) text dropped — neither means anything to a reader outside
retrieval; `text` here is the chunk as written, not what was embedded.

Implemented by `api/services/document_service.get_document_chunks`, served through the
[api package](/packages/api.md).
