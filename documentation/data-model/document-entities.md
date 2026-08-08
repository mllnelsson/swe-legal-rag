---
type: Table
title: document_entities
description: Junction table mapping entities to documents with a relevance weight (primary or mentioned).
resource: postgres://document_entities
tags: [data-model, table, junction, graph]
timestamp: 2026-08-07T00:00:00Z
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

A row linking to a `keyword`-typed [entity](/data-model/entities.md) is always
`primary`, never `mentioned`: a keyword is the nämnd's own statement of what the case is
about, not an incidental mention extraction happened to pick up. That is also why
[`/api/keywords/{id}/documents`](/api/keyword-documents.md), unlike the concept
traversal, takes no `relevance` parameter — there is nothing to narrow by.

Re-extracting a document replaces its full set of rows here rather than adding to it:
[`persist_entities()`](/pipeline/extract.md) deletes any row for the document whose
`entity_id` is not in what the new run just wrote, via
`document_entity.delete_missing_for_document`. This is what makes a corrected extraction
rule visible in the data — without it, the corrected entity set would sit beside the
superseded one it was meant to replace. The corresponding rows in
[`entities`](/data-model/entities.md) are never deleted; an entity nothing links to is
unreachable rather than wrong.
