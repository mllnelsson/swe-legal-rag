---
type: API Endpoint
title: Keywords Endpoint (GET /api/keywords)
description: The GET /api/keywords contract — browsing the nämnd's own Sökord subject classification, most-used first, with the document count each keyword carries.
resource: GET /api/keywords
tags: [api, keywords, rest, entities]
timestamp: 2026-08-03T00:00:00Z
---

# Keywords Endpoint (`GET /api/keywords`)

Browses [entities](/data-model/entities.md) of type `keyword` — the nämnd's own
`Sökord` subject classification, declared on every decision's trailer rather than
inferred from its prose (see [document structure](/reference/document-structure.md)).
Shaped like [`/api/concepts`](/api/concepts.md), and deliberately separate from it: a
caller browsing the graph's *inferred* nodes and a caller browsing the corpus's
*declared* vocabulary are asking different questions, and pinning `entity_type` inside
the service is what keeps that distinction from being a query parameter a caller could
forget. Pairs with [`/api/keywords/{id}/documents`](/api/keyword-documents.md) for the
traversal hop from a keyword to the decisions classified under it.

## Query parameters

| Parameter | Notes |
|---|---|
| `q` | Case-insensitive substring match on the keyword's name, 1-200 chars |
| `limit` / `offset` | Paginated, same clamping as [`/api/documents`](/api/documents.md) |

## Response

```json
{
  "items": [{"id": "uuid", "name": "string", "type": "keyword", "document_count": 0}],
  "total": 0,
  "limit": 10,
  "offset": 0
}
```

Sorted most-cited first (`document_count` descending, then name). A keyword with
`document_count: 0` never appears, the same inner-join-through-`document_entities`
reasoning as [`/api/concepts`](/api/concepts.md).

Implemented by `api/services/keyword_service.list_keywords` →
`shared.repositories.entity.list_entities`/`count_entities` with `entity_type` pinned to
`EntityType.KEYWORD`, served through the [api package](/packages/api.md).
