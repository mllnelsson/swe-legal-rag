---
type: Package
title: shared Package
description: The single source of truth for data and database access — models, DTOs, enums, errors, the task envelope, config, and the storage/queue infrastructure abstractions.
resource: packages/shared
tags: [package, shared, models, dtos, infrastructure]
timestamp: 2026-08-05T00:00:00Z
---

# shared Package (`packages/shared/`)

The single source of truth for data and database access, depended on by every other
package.

## `config.py`

Centralized, pydantic-settings-backed configuration:

| Class | Reads env vars | Purpose |
|---|---|---|
| `DatabaseSettings` | `DATABASE_URL` | Database connection string (required) |
| `StorageSettings` | `STORAGE_BACKEND`, `LOCAL_STORAGE_PATH`, `GCS_BUCKET` | Storage config; defaults to `local` |
| `QueueSettings` | `QUEUE_BACKEND`, `PUBSUB_PROJECT_ID` | Queue config; defaults to `sync` |
| `Settings` | (composes the above) | Root container; access via `get_settings()` |

`StorageBackendType` (`local`, `gcs`) and `QueueBackendType` (`sync`, `pubsub`) are
`StrEnum` types used for exhaustive `match`/`case` dispatch in factories. Cross-field
validators enforce that GCS requires `GCS_BUCKET` and Pub/Sub requires
`PUBSUB_PROJECT_ID`. `get_settings()` returns an `@lru_cache` singleton (call
`get_settings.cache_clear()` between tests). `EMBEDDING_DIMENSION` (int, default `1024`)
is also defined here and imported by the `Chunk` model.

## `models/`

SQLAlchemy 2.x models, one file per table, all using `DeclarativeBase` from
`models/base.py`. Key decisions: `chunks.embedding` is
`pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSION)` (dimension resolved from env at import
time); `chunks.tsv` is a `GENERATED ALWAYS AS (to_tsvector('swedish', chunk_text))
STORED` column via SQLAlchemy `Computed(..., persisted=True)`; `documents.updated_at`
uses `onupdate=func.now()`.

## `dtos/`

Pydantic v2 models per entity: `*Create` (insert input, omits server-generated fields),
`*Read` (full record, `from_attributes=True`), `*Update` (partial, all fields optional —
the progressive-fill pattern). The repo layer enforces the DTO boundary: ORM objects
never escape past the repository. Finite-set DTO fields carry enum *values* but are typed
`str` — see the [architectural register](/decisions/architectural-register.md).
`shared/dtos/search.py` holds `DocumentFilter` (all-optional filter criteria — including
exact-match `case_number`/`decision_number`, distinct from the citation-traversal
`references_case_number`), `ChunkSearchResult`, and the facet types `FacetValue`/
`DocumentFacets`; the `ai`→`DocumentFilter` mapping lives in `api`, since `shared` must
not import from `ai`.

Several DTOs exist purely to carry a **joined read** — an edge with the other side
already resolved to names/case numbers, so a route does not cost a lookup per row:
`DocumentEntityDetail`/`EntityDocumentRef` (`dtos/document_entity.py`),
`ReferenceEdge`/`ReferenceEdges` (`dtos/document_reference.py`), and `EntityWithCount`
(`dtos/entity.py`). The plain `*Read` DTOs they sit alongside carry bare ids only.

## `enums.py`

The single source of truth for finite vocabularies — `TaskStatus`, `PipelineStep`,
`EntityType`, `EntityRelevance`, `ChunkSection`, all `StrEnum`, so each member *is* the
exact string stored in the DB and passed on the queue. `PipelineStep` also names the
queue topic each stage consumes from.

## `segmentation.py`

Pure functions that cut a decision's `raw_text` into `DocumentSegments(body, holding,
trailer, appendices)`, plus `normalize_case_number()` / `normalize_decision_number()` and
`parse_keywords(trailer) -> list[str]`, which reads the nämnd's own subject
classification off the trailer's `Sökord:` line.

It lives in `shared` because the [metadata](/pipeline/metadata.md),
[extract](/pipeline/extract.md) and [chunk](/pipeline/chunk.md) workers all need the same
split, and each previously re-derived (or failed to derive) it locally. No I/O, no
config, never raises. Fully described in
[decision document structure](/reference/document-structure.md).

## `errors.py`

`SharedError` (base), `BackendConfigError` (unknown storage/queue backend), and
`QueueHandlerError` (dispatch to a topic with no handler). Each package that raises its
own domain failures has its own `errors.py`.

## `pipeline.py`

Provides `run_pipeline_step(...)`, the task envelope every subscriber worker runs inside —
see [worker patterns](/pipeline/worker-patterns.md).

## `repositories/`

Modules of async functions, one per entity — the data-access layer. Fully described in
[repositories](/data-model/repositories.md), including the `_protocols.py` injection
seam.

## `search/`

`shared/search/rrf.py` provides `rrf_fuse_scored(rankings, k=DEFAULT_RRF_K) ->
list[tuple[UUID, float]]` — a pure, stateless reciprocal rank fusion (`Σ 1/(k +
rank_i)`) that keeps the fused score and takes arbitrarily many rankings, and
`rrf_fuse(rankings, k=DEFAULT_RRF_K) -> list[UUID]`, a thin wrapper dropping the score.
`DEFAULT_RRF_K = 60` is the named damping constant both use by default. Consumed by the
[retrieval agent](/retrieval/agent.md) (`rrf_fuse`) and [deterministic
search](/retrieval/deterministic-search.md) (`rrf_fuse_scored`, which is what lets an
unbounded number of query-expansion variants fuse through the same call as the two
search arms).

`shared/search/filters.py` provides `is_empty_filter(document_filter: DocumentFilter) ->
bool`, derived via `model_dump(exclude_defaults=True)` rather than enumerating fields by
hand, so a `DocumentFilter` field added later cannot silently go unconsidered. Both the
chat retriever and the search service call it; it replaced a hand-enumerated
`retriever._filter_is_empty`.

## `db.py`

| Function | Purpose |
|---|---|
| `get_engine()` | Cached sync `Engine` (`postgresql+psycopg://`), used by Alembic |
| `get_session()` | Sync context manager, used for Alembic offline mode |
| `get_async_session()` | Async context manager yielding an `AsyncSession` with auto commit/rollback — used by application code |
| `dispose_async_engine()` | Closes the running loop's async engine and its pooled connections |

`get_engine()` is `@lru_cache` so the connection pool is shared; `pool_pre_ping=True`
validates connections. `DATABASE_URL` is read from `get_settings()`, not `os.environ`
directly; the async engine uses `postgresql+asyncpg://` (scheme normalized regardless of
input).

**The async engine is per event loop, not per process.** An asyncpg connection belongs to
the loop that opened it, so a pooled connection handed to a second `asyncio.run()` fails
with `RuntimeError: ... got Future attached to a different loop`. `get_async_session()`
therefore keys its engine on `asyncio.get_running_loop()`. A process with one long-lived
loop (the API server) gets one engine and a normal pool; workers run
[one loop per message](/pipeline/worker-patterns.md) and so get one engine each, which
they must dispose before that loop closes — `shared.worker` does this for every message,
and any other code owning a loop for one unit of work has to do the same or leak a
connection per loop.

## Infrastructure abstractions — `storage/` and `queue/`

`config.py`, `storage/`, and `queue/` form the infrastructure abstraction layer: each
concern is a Protocol, a set of backend implementations, and a factory selecting the
backend from env vars — making local ↔ GCP a config change (see
[GCP layout](/reference/gcp-layout.md)).

**Storage** — `StorageBackend` Protocol: `store`, `retrieve`, `exists`, `delete`,
`get_url`. `LocalStorageBackend` (under `LOCAL_STORAGE_PATH`) and `GCSStorageBackend`
(wraps `google-cloud-storage`, needs `GCS_BUCKET`). `create_storage_backend(settings)`
lazy-imports GCS libs. Optional dep: `uv add 'shared[gcs]'`.

`shared/storage/keys.py` provides `document_pdf_key(document_id) -> str` —
`documents/{id}/original.pdf`. It replaces the same literal template that used to be
duplicated in the [download](/pipeline/download.md) and [parse](/pipeline/parse.md)
workers and in `api/services/answerer.py`; all three, plus the new [PDF
endpoint](/api/document-pdf.md), now call the one helper, since the layout is a contract
shared across packages rather than any one caller's detail.

### Why it is only a blob store

The Protocol is deliberately five methods wide. It carries no notion of appending, of
JSON, or of a record — a key maps to a blob of bytes and nothing more, so the two
backends have no behaviour to diverge on and a third would have nothing extra to
implement.

The pressure to widen it came from LLM trace capture, which wants an append-style
stream. That belongs to the writer, not the storage layer: the trace recorder batches
records, serializes the batch as JSONL, and writes it with `store` under a key it
chooses itself. An object store cannot append, but it never has to — a batch is a whole
object. Local and GCS therefore hold byte-identical contents under identical keys. See
[LLM Observability](/observability.md).

**Queue** — `QueueMessage(task_id, document_id, payload)` maps 1:1 to task rows;
`QueuePublisher.publish(topic, message)` and `QueueSubscriber.subscribe/start/shutdown`
Protocols. `sync` backend (`SyncQueuePublisher/Subscriber` over a module-level
`SyncQueueBroker` singleton shared by publisher and subscriber — `publish` **queues**,
`start()` pumps until the queue empties) and `pubsub` backend (GCP Pub/Sub via streaming
pull, JSON-serialized). Queueing rather than calling the handler inline is what lets each
step own its event loop: every publish happens inside the publishing step's loop, and a
handler needs a loop of its own. An unsubscribed topic still raises `QueueHandlerError`
at publish time. `create_queue_publisher/subscriber(settings)` select by `QUEUE_BACKEND`.
Optional deps: `uv add 'shared[pubsub]'`, or `'shared[gcp]'` for both.
