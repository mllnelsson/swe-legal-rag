---
type: Table
title: entities
description: Extracted legal concepts, roles, parishes, and regulations — the nodes of the in-Postgres knowledge graph.
resource: postgres://entities
tags: [data-model, table, entities, graph]
timestamp: 2026-07-24T00:00:00Z
---

# `entities`

Extracted entities from the corpus. Legal concepts, roles, parishes, regulations.
Enables graph-style pre-filtering without a graph database (see
[architectural register](/decisions/architectural-register.md)).

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR | Normalized entity name |
| type | VARCHAR | `legal_concept`, `role`, `parish`, `regulation` |
| created_at | TIMESTAMPTZ | Row creation |

Unique constraint on `(name, type)`. `type` values come from the `EntityType` `StrEnum`
in `shared.enums` (see [design notes](/data-model/design-notes.md)). Entities are
produced by the [extract worker](/pipeline/extract.md) and linked to documents via
[document_entities](/data-model/document-entities.md).
