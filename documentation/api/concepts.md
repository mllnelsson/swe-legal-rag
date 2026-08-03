---
type: API Endpoint
title: Concepts Endpoint (GET /api/concepts)
description: The GET /api/concepts contract — browsing the knowledge graph's nodes (legal concepts, regulations, roles, parishes) with the document count each carries, optionally filtered by type or name.
resource: GET /api/concepts
tags: [api, concepts, rest, entities]
timestamp: 2026-08-03T00:00:00Z
---

# Concepts Endpoint (`GET /api/concepts`)

Browses [entities](/data-model/entities.md) — the graph's nodes. Pairs with
[`/api/concepts/{id}/documents`](/api/concept-documents.md) for the traversal hop from a
concept to the decisions naming it.

## Query parameters

| Parameter | Notes |
|---|---|
| `entity_type` | One `EntityType` member |
| `q` | Case-insensitive substring match on the entity's name, 1-200 chars |
| `limit` / `offset` | Paginated, same clamping as [`/api/documents`](/api/documents.md) |

## Response

```json
{
  "items": [{"id": "uuid", "name": "string", "type": "string", "document_count": 0}],
  "total": 0,
  "limit": 10,
  "offset": 0
}
```

Sorted most-cited first (`document_count` descending, then name). An entity with
`document_count: 0` never appears: the underlying query is an inner join through
[document_entities](/data-model/document-entities.md), so an entity with no documents is
a dead end with nothing to traverse to, and is dropped rather than listed.

Implemented by `api/services/concept_service.list_concepts` →
`shared.repositories.entity.list_entities`/`count_entities`, served through the [api
package](/packages/api.md).
