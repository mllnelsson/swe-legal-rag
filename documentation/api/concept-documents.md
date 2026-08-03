---
type: API Endpoint
title: Concept Documents Endpoint (GET /api/concepts/{id}/documents)
description: The GET /api/concepts/{id}/documents contract — every decision carrying a given entity, the reverse traversal hop from a concept back to the decisions that name it.
resource: GET /api/concepts/{entity_id}/documents
tags: [api, concepts, rest, entities, traversal]
timestamp: 2026-08-03T00:00:00Z
---

# Concept Documents Endpoint (`GET /api/concepts/{entity_id}/documents`)

One hop through the graph: from an entity — surfaced on a document's [detail
view](/api/document-detail.md) or via [`/api/concepts`](/api/concepts.md) — to every
decision that names it.

404s when `entity_id` is unknown, distinguished from "a concept with no decisions" (a
200 with an empty `items`), so a caller can tell "no such concept" apart from "nothing
found".

## Query parameters

| Parameter | Notes |
|---|---|
| `relevance` | One `EntityRelevance` member (`primary`/`mentioned`); omitted returns both |
| `limit` / `offset` | Paginated |

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
      "relevance": "primary | mentioned"
    }
  ],
  "total": 0,
  "limit": 10,
  "offset": 0
}
```

Sorted `primary` relevance first, then newest `decision_date`. This is the first caller
to query [document_entities](/data-model/document-entities.md)`.relevance` rather than
merely storing it — see that table's concept.

Implemented by `api/services/concept_service.list_documents_for_concept` →
`shared.repositories.document_entity.list_documents_for_entity`/`count_documents_for_entity`,
served through the [api package](/packages/api.md).
