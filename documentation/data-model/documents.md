---
type: Table
title: documents
description: The document registry — one row per PDF, tracking both identity and progressive ingestion state.
resource: postgres://documents
tags: [data-model, table, documents, registry]
timestamp: 2026-07-26T00:00:00Z
---

# `documents`

The registry. One row per PDF. Tracks both identity and ingestion progress.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| source_url | TEXT | Canonical PDF URL, keyed on the CMS document id (`default.aspx?id=...`). Unique constraint — dedup key. |
| source_document_id | INTEGER | Nullable. CMS `documentId` from the OData listing. Unique constraint — second dedup backstop. Null for rows predating the OData crawler. |
| source_headline | TEXT | Nullable. Headline from the OData listing, set at crawl time |
| source_published_at | TIMESTAMPTZ | Nullable. Publish date from the OData listing, set at crawl time |
| gcs_uri | TEXT | Nullable. Set after download step |
| raw_text | TEXT | Nullable. Set after parse step |
| summary | TEXT | Nullable. Set after chunking step (document-level summary) |
| case_number | VARCHAR | Nullable. Ärendenummer, canonical `YYYY-NNNN`. Set after metadata step |
| decision_number | VARCHAR | Nullable. Beslutsnummer, canonical `N/YYYY` — a separate identifier space from `case_number`. Set after metadata step |
| decision_date | DATE | Nullable. Set after metadata step |
| decision_outcome | VARCHAR | Nullable. Set after metadata step |
| category | VARCHAR | Nullable. Set after metadata step |
| created_at | TIMESTAMPTZ | Row creation |
| updated_at | TIMESTAMPTZ | Last modification |

The nullable columns are filled progressively — each pipeline step writes its own
fields, so the row doubles as an ingestion-progress record (see [design
notes](/data-model/design-notes.md)). The `source_*` columns come from the OData listing
at crawl time; see [crawl source](/reference/crawl-source.md). Column ownership by step:
`gcs_uri` ← [download](/pipeline/download.md), `raw_text` ←
[parse](/pipeline/parse.md),
`case_number`/`decision_number`/`decision_date`/`decision_outcome`/`category` ←
[metadata](/pipeline/metadata.md), `summary` ← [chunk](/pipeline/chunk.md).

A decision carries **two** identifiers and cites other decisions by either, so both must
be resolvable — a `beslut 13/2025` citation cannot match `case_number`. The canonical
forms are disjoint (a beslutsnummer always contains `/`), which is how
[reference resolution](/data-model/document-references.md) knows which column to query.
See [decision document structure](/reference/document-structure.md).
