---
type: Table
title: document_references
description: Resolved cross-citations between decisions — one decision citing another as precedent.
resource: postgres://document_references
tags: [data-model, table, references, graph]
timestamp: 2026-07-24T00:00:00Z
---

# `document_references`

Cross-citations between decisions. Captures when one decision references another as
precedent.

| Column | Type | Notes |
|---|---|---|
| source_document_id | UUID | FK → [documents](/data-model/documents.md) (the citing decision) |
| target_document_id | UUID | FK → [documents](/data-model/documents.md) (the cited decision) |
| reference_context | TEXT | Nullable. The sentence/context in which the citation occurs |

Composite PK on `(source_document_id, target_document_id)`. `target_document_id` is a
non-nullable FK; citations whose target is not yet in the corpus are held in
[unresolved_references](/data-model/unresolved-references.md) until the target is
ingested. Populated by the [extract worker](/pipeline/extract.md); used by the
[retrieval agent](/retrieval/agent.md) for relationship traversal ("what other decisions
cite this one?").
