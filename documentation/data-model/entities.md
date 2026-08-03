---
type: Table
title: entities
description: Extracted legal concepts, roles, parishes, regulations, and declared keywords — the nodes of the in-Postgres knowledge graph.
resource: postgres://entities
tags: [data-model, table, entities, graph]
timestamp: 2026-08-03T00:00:00Z
---

# `entities`

Extracted entities from the corpus. Legal concepts, roles, parishes, regulations, and
keywords. Enables graph-style pre-filtering without a graph database (see
[architectural register](/decisions/architectural-register.md)).

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR | Normalized entity name |
| type | VARCHAR | `legal_concept`, `role`, `parish`, `regulation`, `keyword` |
| created_at | TIMESTAMPTZ | Row creation |

Unique constraint on `(name, type)`. `type` values come from the `EntityType` `StrEnum`
in `shared.enums` (see [design notes](/data-model/design-notes.md)). Entities are
produced by the [extract worker](/pipeline/extract.md) and linked to documents via
[document_entities](/data-model/document-entities.md).

`keyword` differs from the other four in provenance rather than shape: `legal_concept`,
`role`, `parish` and `regulation` are *inferred* from a decision's prose by regex or LLM,
while a `keyword` is *declared* by Överklagandenämnden itself, on the trailer's `Sökord:`
line (see [document structure](/reference/document-structure.md)). Adding it needed no
migration and no new table — it is a fifth value of an existing `StrEnum` landing in a
column already typed `VARCHAR`, the same "vocabulary member is free" property recorded in
the [architectural register](/decisions/architectural-register.md).
