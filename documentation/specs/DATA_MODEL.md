# Data Model Spec: Överklagandenämnden Decision Search Tool

## Core Tables

### `documents`

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
| case_number | VARCHAR | Nullable. Set after metadata step |
| decision_date | DATE | Nullable. Set after metadata step |
| decision_outcome | VARCHAR | Nullable. Set after metadata step |
| category | VARCHAR | Nullable. Set after metadata step |
| created_at | TIMESTAMPTZ | Row creation |
| updated_at | TIMESTAMPTZ | Last modification |

### `tasks`

One row per document per pipeline step. Each task represents a unit of work: "process document X through step Y." Queue messages map 1:1 to task rows.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| document_id | UUID | FK → documents |
| step | VARCHAR | `crawl`, `download`, `parse`, `metadata`, `extract`, `chunk`, `embed` |
| status | VARCHAR | `pending`, `processing`, `completed`, `failed` |
| error_message | TEXT | Nullable. Populated on failure |
| started_at | TIMESTAMPTZ | Nullable |
| completed_at | TIMESTAMPTZ | Nullable |

Unique constraint on `(document_id, step)`. Resumability: query for tasks where a given step is not `completed`.

### `chunks`

The retrieval layer. Each chunk is a unit of search and retrieval.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| document_id | UUID | FK → documents |
| chunk_index | INTEGER | Position within document (ordering) |
| chunk_text | TEXT | Raw chunk content. Displayed in citations. |
| contextual_text | TEXT | Summary + chunk text. Used for embedding. Never shown to end users. |
| embedding | VECTOR(1024) | pgvector. Width is set by the embedding model — see [Embedding dimension](#implementation-decisions) |
| tsv | TSVECTOR | Generated from chunk_text using Swedish text search config. For BM25-style search. |
| created_at | TIMESTAMPTZ | Row creation |

### `entities`

Extracted entities from the corpus. Legal concepts, roles, parishes, regulations. Enables graph-style pre-filtering without a graph database.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR | Normalized entity name |
| type | VARCHAR | `legal_concept`, `role`, `parish`, `regulation` |
| created_at | TIMESTAMPTZ | Row creation |

Unique constraint on `(name, type)`.

### `document_entities`

Junction table. Maps entities to documents with relevance weight.

| Column | Type | Notes |
|---|---|---|
| document_id | UUID | FK → documents |
| entity_id | UUID | FK → entities |
| relevance | VARCHAR | `primary` (central to decision) or `mentioned` (referenced) |

Composite PK on `(document_id, entity_id)`.

### `document_references`

Cross-citations between decisions. Captures when one decision references another as precedent.

| Column | Type | Notes |
|---|---|---|
| source_document_id | UUID | FK → documents (the citing decision) |
| target_document_id | UUID | FK → documents (the cited decision) |
| reference_context | TEXT | Nullable. The sentence/context in which the citation occurs |

Composite PK on `(source_document_id, target_document_id)`.

### `unresolved_references`

Temporary storage for cross-references where the target document is not yet in the corpus. Used for lazy resolution: when the target is later ingested and its `case_number` becomes known, `reconcile_references()` promotes these rows to `document_references`.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| source_document_id | UUID | FK → documents (the citing document) |
| target_case_number | VARCHAR | The case number string cited (e.g. `ÖN 2021-0345`) |
| reference_context | TEXT | Nullable. The sentence where the citation occurs |
| created_at | TIMESTAMPTZ | Row creation |

Unique constraint on `(source_document_id, target_case_number)` — same reference can't be stored twice.

### `sessions` (optional)

Conversation history for follow-up support. Can live in-memory or Redis instead if cross-restart persistence isn't needed.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| created_at | TIMESTAMPTZ | |
| last_active_at | TIMESTAMPTZ | For TTL cleanup |
| history | JSONB | Array of message objects `[{role, content, timestamp}]` |

## Indexes

| Table | Index Type | Column(s) | Purpose |
|---|---|---|---|
| chunks | HNSW | embedding | Approximate nearest neighbor vector search |
| chunks | GIN | tsv | Full-text search on Swedish lexemes |
| chunks | btree | document_id | Fast joins back to document metadata |
| tasks | btree | (document_id, step) | Unique constraint + lookup by document |
| tasks | btree | (step, status) | Query for retryable/pending tasks per step |
| documents | btree | source_url | Unique constraint — dedup on crawl |
| documents | btree | source_document_id | Unique constraint — dedup on the CMS document id |
| entities | btree | (name, type) | Unique constraint + lookup by entity |
| entities | btree | type | Filter entities by type |
| document_entities | btree | entity_id | Find all documents for a given entity |
| document_entities | btree | document_id | Find all entities for a given document |
| document_references | btree | target_document_id | Find all decisions that cite a given decision |
| unresolved_references | btree | target_case_number | Reconciliation lookup when a new document is ingested |
| unresolved_references | btree | source_document_id | Find all pending refs for a given source document |

## Implementation Decisions

- **Embedding dimension**: `VECTOR(1024)` for `intfloat/multilingual-e5-large`, selected for Swedish retrieval quality — see [ARCHITECTURE.md §7](ARCHITECTURE.md#7-embedding-model). Configurable via `EMBEDDING_DIMENSION`, default `1024`.

  **`EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` must always change together**, plus a migration recreating the `chunks.embedding` column at the new width. Vectors are not portable across models: e5-base (768) and e5-large (1024) occupy different vector spaces, so a model change invalidates every stored embedding and requires a full re-embed of the corpus.

  **Known hazard — the value is defined in three places and nothing cross-checks them:**

  | Location | When it is read |
  |---|---|
  | `shared/config.py` (`DEFAULT_EMBEDDING_DIMENSION`) | Python import time — configures the `Chunk` model |
  | `alembic/versions/001_initial_schema.py` | `alembic upgrade` time — baked into the DDL |
  | `ai/embedding.py` (`DEFAULT_EMBEDDING_MODEL`) | Implicitly, via the model's actual output width |

  `EMBEDDING_DIMENSION` is read with a bare `os.environ.get` rather than a pydantic setting, so nothing validates these against each other by construction. Setting `EMBEDDING_MODEL` without setting `EMBEDDING_DIMENSION` is the most likely way to break them apart.

  **Guarded by a startup check.** `ai.verify_embedding_dimension(provider)` embeds one throwaway string and compares the observed width against `EMBEDDING_DIMENSION`, raising `EmbeddingDimensionMismatchError` if they disagree. It runs in `worker-embed`'s `__main__` before the queue subscription starts, and in the API's lifespan before it serves traffic. Without it a mismatch surfaced only at the embed step as `EmbeddingDimensionError` (`worker_embed/service.py`) — after crawl, download, parse, metadata, extract and chunk had already run.

  The check is written against the `EmbeddingProvider` Protocol, not the local provider, so a future HTTP-backed provider is covered unchanged. Because it performs a real embed call, it also forces the local model to load eagerly — see the note in [EMBEDDING_HOSTING.md](../design/EMBEDDING_HOSTING.md).
- **tsvector column**: `chunks.tsv` is a `GENERATED ALWAYS AS (to_tsvector('swedish', chunk_text)) STORED` column. PostgreSQL computes and stores it automatically at INSERT time when `chunk_text` is written (during the chunk step). The embed worker does not touch it — attempting to UPDATE a `GENERATED ALWAYS STORED` column fails with a PostgreSQL error.
- **Async repositories**: The repositories are **modules of async functions** (one per entity), each taking a SQLAlchemy `AsyncSession` as its first argument — not classes. Application code accesses the database exclusively through the async path. See [BACKEND_DESIGN.md → Function-based data layer](../design/BACKEND_DESIGN.md#function-based-data-layer).
- **Finite-set columns stay `str`, values come from `StrEnum`**: `tasks.step`/`status`, `entities.type`, and `document_entities.relevance` are `VARCHAR`/`Mapped[str]`; their values are the `shared.enums` StrEnum members (`PipelineStep`, `TaskStatus`, `EntityType`, `EntityRelevance`). Because a `StrEnum` member is the exact stored text, adopting the enums needed **no migration**.

## Design Notes

- **Nullable metadata fields:** Each pipeline step fills in its columns progressively. A document with `gcs_uri` set but `raw_text` null means download succeeded but parsing hasn't run yet. Combined with `tasks` this gives full observability.
- **`contextual_text` vs `chunk_text`:** Stored separately. `chunk_text` is what the user sees in citations. `contextual_text` (document summary prepended via `summary\n\n---\n\nchunk_text`) is what gets embedded and searched against. Never shown to end users.
- **tsvector Swedish config:** Postgres supports Swedish stemming and stop words via `to_tsvector('swedish', chunk_text)`. Populated automatically via `GENERATED ALWAYS AS ... STORED` at chunk INSERT time — no application-side maintenance.
- **Idempotency pattern:** Re-processing a document deletes existing chunks before re-inserting (DELETE+INSERT). Embeddings are updated in-place via UPDATE on the `embedding` column — no chunk rows are recreated.
- **Chunk sizing rationale:** ~500 tokens per chunk balances retrieval granularity with context preservation. Sentence-aware boundaries prevent mid-sentence splits. 50-token overlap preserves cross-boundary context for embedding.
- **No soft deletes.** If a document needs reprocessing, wipe its chunks, reset its tasks. Keep it simple at this scale.
- **Task-queue alignment:** When a pipeline step publishes to the next Pub/Sub topic, it also inserts a `pending` task row for the next step. The consuming worker updates that row through its lifecycle.
- **Listing metadata is persisted at crawl time (migration 003):** the Svenska kyrkan OData listing supplies `documentId`, `headline` and `publishDate` for free, so they are stored rather than discarded. `source_document_id` gives a stable numeric identity that survives file renames and backs a second unique constraint; `source_headline` and `source_published_at` let the metadata step cross-check the case number and date it extracts from the PDF text. All three are nullable so rows created by the earlier HTML scraper survive the migration — Postgres allows repeated NULLs under a UNIQUE constraint, so those legacy rows do not collide. See [CRAWL_SOURCE.md](../design/CRAWL_SOURCE.md).

- **Graph-in-Postgres:** The `entities`, `document_entities`, and `document_references` tables capture GraphRAG concepts without a graph database. The agent uses these for entity-based pre-filtering (e.g. "find all documents where entity X is primary → semantic search within that set") and relationship traversal ("what other decisions cite this one?"). Standard SQL joins replace graph queries at this scale.
- **Unresolved references:** Cross-references where the target is not yet in the corpus are stored in `unresolved_references` rather than dropped. Reconciliation happens automatically when the target document is ingested (worker-extract's `reconcile_references()`). This keeps `document_references.target_document_id` as a non-nullable FK without loss of reference data.
