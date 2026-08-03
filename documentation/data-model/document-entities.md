---
type: Table
title: document_entities
description: Junction table mapping entities to documents with a relevance weight (primary or mentioned).
resource: postgres://document_entities
tags: [data-model, table, junction, graph]
timestamp: 2026-08-03T00:00:00Z
---

# `document_entities`

Junction table. Maps [entities](/data-model/entities.md) to
[documents](/data-model/documents.md) with relevance weight.

| Column | Type | Notes |
|---|---|---|
| document_id | UUID | FK → documents |
| entity_id | UUID | FK → entities |
| relevance | VARCHAR | `primary` (central to decision) or `mentioned` (referenced) |

Composite PK on `(document_id, entity_id)`. `relevance` values come from the
`EntityRelevance` `StrEnum` in `shared.enums` (see
[design notes](/data-model/design-notes.md)). Populated by the
[extract worker](/pipeline/extract.md); used by the [retrieval agent](/retrieval/agent.md)
for entity-based pre-filtering, by [`/api/documents/{id}`](/api/document-detail.md) to
list a document's concepts, and by
[`/api/concepts/{id}/documents`](/api/concept-documents.md) — the first caller to filter
on `relevance` rather than only storing it.
