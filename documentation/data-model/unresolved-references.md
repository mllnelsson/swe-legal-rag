---
type: Table
title: unresolved_references
description: Lazy-resolution store for citations whose target decision is not yet in the corpus.
resource: postgres://unresolved_references
tags: [data-model, table, references, reconciliation]
timestamp: 2026-07-26T00:00:00Z
---

# `unresolved_references`

Temporary storage for cross-references where the target document is not yet in the
corpus. Used for lazy resolution: when the target is later ingested and its identifiers
become known, `reconcile_references()` promotes these rows to
[document_references](/data-model/document-references.md).

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| source_document_id | UUID | FK → [documents](/data-model/documents.md) (the citing document) |
| target_case_number | VARCHAR | The canonical identifier cited — an ärendenummer (`2021-0345`) or a beslutsnummer (`13/2025`). The two spaces share this column; the format tells them apart. |
| reference_context | TEXT | Nullable. The sentence where the citation occurs |
| created_at | TIMESTAMPTZ | Row creation |

Unique constraint on `(source_document_id, target_case_number)` — the same reference
can't be stored twice. Reconciliation runs automatically when a new document is ingested
(the [extract worker](/pipeline/extract.md)'s `reconcile_references()`), keeping
`document_references.target_document_id` a non-nullable FK without losing reference data.

Reconciliation queries **both** of the arriving document's identifiers, so a decision
cited as `2025-0017` by one document and `1/2026` by another collects both. Values are
stored canonicalised (no `ÖN ` prefix) — see
[decision document structure](/reference/document-structure.md); without one canonical
form the stored spelling never matched `documents.case_number` and nothing ever
resolved.
