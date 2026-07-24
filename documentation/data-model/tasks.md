---
type: Table
title: tasks
description: One row per document per pipeline step — the unit of work that queue messages map to 1:1.
resource: postgres://tasks
tags: [data-model, table, tasks, pipeline]
timestamp: 2026-07-24T00:00:00Z
---

# `tasks`

One row per document per pipeline step. Each task represents a unit of work: "process
document X through step Y." Queue messages map 1:1 to task rows.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| document_id | UUID | FK → [documents](/data-model/documents.md) |
| step | VARCHAR | `crawl`, `download`, `parse`, `metadata`, `extract`, `chunk`, `embed` |
| status | VARCHAR | `pending`, `processing`, `completed`, `failed` |
| error_message | TEXT | Nullable. Populated on failure |
| started_at | TIMESTAMPTZ | Nullable |
| completed_at | TIMESTAMPTZ | Nullable |

Unique constraint on `(document_id, step)`. Resumability: query for tasks where a given
step is not `completed`.

`step` and `status` are `VARCHAR` columns whose values come from the `PipelineStep` and
`TaskStatus` `StrEnum`s in `shared.enums` (see [design
notes](/data-model/design-notes.md)). The task lifecycle is driven by the shared task
envelope — see [worker patterns](/pipeline/worker-patterns.md) and the
[pipeline overview](/pipeline/overview.md).
