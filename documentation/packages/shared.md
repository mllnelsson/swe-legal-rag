---
type: Package
title: shared Package
description: The single source of truth for data and database access — models, DTOs, enums, errors, the task envelope, config, and the storage/queue infrastructure abstractions.
resource: packages/shared
tags: [package, shared, models, dtos, infrastructure]
timestamp: 2026-07-27T00:00:00Z
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
`shared/dtos/search.py` holds `DocumentFilter` (all-optional filter criteria) and
`ChunkSearchResult`; the `ai`→`DocumentFilter` mapping lives in `api`, since `shared` must
not import from `ai`.

## `enums.py`

The single source of truth for finite vocabularies — `TaskStatus`, `PipelineStep`,
`EntityType`, `EntityRelevance`, `ChunkSection`, all `StrEnum`, so each member *is* the
exact string stored in the DB and passed on the queue. `PipelineStep` also names the
queue topic each stage consumes from.

## `segmentation.py`

Pure functions that cut a decision's `raw_text` into `DocumentSegments(body, holding,
trailer, appendices)`, plus `normalize_case_number()` / `normalize_decision_number()`.

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

`shared/search/rrf.py` provides `rrf_fuse(rankings, k=60) -> list[UUID]` — a pure,
stateless reciprocal rank fusion (`Σ 1/(k + rank_i)`), consumed by the
[retrieval agent](/retrieval/agent.md).

## `db.py`

| Function | Purpose |
|---|---|
| `get_engine()` | Cached sync `Engine` (`postgresql+psycopg://`), used by Alembic |
| `get_session()` | Sync context manager, used for Alembic offline mode |
| `get_async_session()` | Async context manager yielding an `AsyncSession` with auto commit/rollback — used by application code |

`get_engine()` is `@lru_cache` so the connection pool is shared; `pool_pre_ping=True`
validates connections. `DATABASE_URL` is read from `get_settings()`, not `os.environ`
directly; the async engine uses `postgresql+asyncpg://` (scheme normalized regardless of
input).

## Infrastructure abstractions — `storage/` and `queue/`

`config.py`, `storage/`, and `queue/` form the infrastructure abstraction layer: each
concern is a Protocol, a set of backend implementations, and a factory selecting the
backend from env vars — making local ↔ GCP a config change (see
[GCP layout](/reference/gcp-layout.md)).

**Storage** — `StorageBackend` Protocol, in two halves. Blobs: `store`, `retrieve`,
`exists`, `delete`, `get_url`. Append-style JSON streams: `add_json(key, record)` and
`iter_json(prefix)`. `LocalStorageBackend` (under `LOCAL_STORAGE_PATH`) and
`GCSStorageBackend` (wraps `google-cloud-storage`, needs `GCS_BUCKET`).
`create_storage_backend(settings)` lazy-imports GCS libs. Optional dep:
`uv add 'shared[gcs]'`.

### JSON streams

`add_json` takes an **extension-free logical stream key** (`llm-traces/2026-07-27`), not
a file name. The two backends lay a stream out differently, because an object store
cannot append:

| Backend | One stream is |
|---|---|
| Local | One `.jsonl` file, one record per line |
| GCS | One prefix holding one object per record |

The divergence is deliberate and stays behind the Protocol — callers write with
`add_json` and read with `iter_json` and never learn which backend they have. That
symmetry is also why there is no `list_keys`: a key list would re-expose the difference,
since one key means "many records" locally and "one record" on GCS.

Records within a stream are **unordered**; key order approximates write order on GCS and
completion order locally, and neither is total. Sort on a field of the record.

Local appends take an exclusive `flock`. `O_APPEND` is atomic only below `PIPE_BUF`
(4096 bytes) and records can run to tens of kilobytes, so concurrent worker processes
would otherwise interleave partial lines. The lock is advisory, which holds only because
the Protocol is the single door. Without `fcntl` (non-POSIX hosts) the fallback guards
threads but not processes.

The one production consumer today is LLM trace capture — see
[LLM Observability](/observability.md).

**Queue** — `QueueMessage(task_id, document_id, payload)` maps 1:1 to task rows;
`QueuePublisher.publish(topic, message)` and `QueueSubscriber.subscribe/start/shutdown`
Protocols. `sync` backend (`SyncQueuePublisher/Subscriber`, in-process — publish directly
invokes the registered handler; a module-level `SyncQueueBroker` singleton is shared by
publisher and subscriber) and `pubsub` backend (GCP Pub/Sub via streaming pull,
JSON-serialized). `create_queue_publisher/subscriber(settings)` select by `QUEUE_BACKEND`.
Optional deps: `uv add 'shared[pubsub]'`, or `'shared[gcp]'` for both.
