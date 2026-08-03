---
type: API Endpoint
title: Keyword Documents Endpoint (GET /api/keywords/{id}/documents)
description: The GET /api/keywords/{id}/documents contract — every decision classified under a given Sökord keyword, the reverse traversal hop from a keyword back to the decisions that declare it.
resource: GET /api/keywords/{keyword_id}/documents
tags: [api, keywords, rest, entities, traversal]
timestamp: 2026-08-03T00:00:00Z
---

# Keyword Documents Endpoint (`GET /api/keywords/{keyword_id}/documents`)

One hop through the graph: from a keyword — surfaced on a document's [detail
view](/api/document-detail.md) or via [`/api/keywords`](/api/keywords.md) — to every
decision classified under it.

404s when `keyword_id` is unknown **or names an entity of some other type**: every
keyword is an entity, but this endpoint promises the reverse, and silently answering for
a legal concept's id would make the two indistinguishable to a caller paging through ids.
This is distinct from "a keyword with no decisions" (a 200 with an empty `items`), so a
caller can tell "no such keyword" apart from "nothing found".

## Query parameters

| Parameter | Notes |
|---|---|
| `limit` / `offset` | Paginated |

Unlike [`/api/concepts/{id}/documents`](/api/concept-documents.md), there is deliberately
**no `relevance` parameter**: a
[declared keyword is always `primary`](/data-model/document-entities.md), so there is
nothing to narrow by.

## Response

```json
{
  "items": [
    {
      "document_id": "uuid",
      "case_number": "string | null",
      "decision_number": "string | null",
      "decision_date": "date | null",
      "headline": "string | null",
      "category": "string | null",
      "decision_outcome": "string | null",
      "relevance": "primary"
    }
  ],
  "total": 0,
  "limit": 10,
  "offset": 0
}
```

Sorted newest `decision_date` first (nulls last, `document_id` tiebreak) — the same
`list_documents_for_entity` ordering [`/api/concepts/{id}/documents`](/api/concept-documents.md)
uses, whose primary-first tiebreak never has anything to break here since every row is
`primary`.

Implemented by `api/services/keyword_service.list_documents_for_keyword` →
`shared.repositories.document_entity.list_documents_for_entity`/`count_documents_for_entity`,
served through the [api package](/packages/api.md).
