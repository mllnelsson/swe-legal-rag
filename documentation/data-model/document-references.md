---
type: Table
title: document_references
description: Resolved cross-citations between decisions — one decision citing another as precedent.
resource: postgres://document_references
tags: [data-model, table, references, graph]
timestamp: 2026-08-03T00:00:00Z
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
[retrieval agent](/retrieval/chat-agent.md) for relationship traversal ("what other decisions
cite this one?").

Citations are matched in **two identifier spaces** — `documents.case_number`
(`2025-0017`) and `documents.decision_number` (`1/2026`). The canonical forms are
disjoint, so the reference string itself selects the column. Only citations found in the
decision **body** are recorded: the trailer holds the document's own identifiers, and an
appendix citation belongs to the appealed instance rather than to Överklagandenämnden.
See [decision document structure](/reference/document-structure.md).

[`/api/documents/{id}`](/api/document-detail.md) resolves both directions of a
document's edges to the other document's identity — two queries total, not one per edge
— and renders them as `references_out`/`references_in`.
