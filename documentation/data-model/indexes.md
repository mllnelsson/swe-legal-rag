---
type: Reference
title: Indexes
description: The index catalog across all tables — HNSW/GIN for retrieval, btree for constraints and lookups.
tags: [data-model, indexes, pgvector, performance]
timestamp: 2026-08-08T00:00:00Z
---

# Indexes

| Table | Index Type | Column(s) | Purpose |
|---|---|---|---|
| [chunks](/data-model/chunks.md) | HNSW | embedding | Approximate nearest neighbor vector search |
| chunks | GIN | tsv | Full-text search on Swedish lexemes |
| chunks | btree | document_id | Fast joins back to document metadata |
| chunks | btree | section | Scope search to the nämnd's own text — see [body-first retrieval](/decisions/body-first-retrieval.md) |
| [tasks](/data-model/tasks.md) | btree | (document_id, step) | Unique constraint + lookup by document |
| tasks | btree | (step, status) | Query for retryable/pending tasks per step |
| [documents](/data-model/documents.md) | btree | source_url | Unique constraint — dedup on crawl |
| documents | btree | source_document_id | Unique constraint — dedup on the CMS document id |
| documents | btree | source_decision_number | Unique constraint — the actual crawl dedup key, the beslutsnummer parsed from the listing headline |
| documents | btree | decision_number | Resolve `beslut N/YYYY` citations to a document |
| [entities](/data-model/entities.md) | btree | (name, type) | Unique constraint + lookup by entity |
| entities | btree | type | Filter entities by type |
| [document_entities](/data-model/document-entities.md) | btree | entity_id | Find all documents for a given entity |
| document_entities | btree | document_id | Find all entities for a given document |
| [document_references](/data-model/document-references.md) | btree | target_document_id | Find all decisions that cite a given decision |
| [unresolved_references](/data-model/unresolved-references.md) | btree | target_case_number | Reconciliation lookup when a new document is ingested |
| unresolved_references | btree | source_document_id | Find all pending refs for a given source document |
