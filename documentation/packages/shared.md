---
type: Package
title: shared Package
description: The single source of truth for data and database access — models, DTOs, enums, errors, the task envelope, config, logging setup, and the storage/queue infrastructure abstractions.
resource: packages/shared
tags: [package, shared, models, dtos, infrastructure]
timestamp: 2026-08-14T00:00:00Z
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
see [worker patterns](/pipeline/worker-patterns.md). It logs each step's start, duration
and outcome, so a worker that logs nothing of its own is still visible in a run. The API
has the same shape one layer up, in `api.access_log` — see
[application logging](/logging.md).

## `logging_config.py`

Provides `configure_logging(level=None)` and `resolve_log_level()` — the single
root-logger configuration (timestamped `HH:MM:SS levelname name: message`) every entry
point installs. Called from each `main()`, never at import: `scripts/run_pipeline.py`
imports six workers before it runs a line of its own, and `logging.basicConfig` is a
no-op once the root logger has a handler, so import-time configuration made the format
depend on import order. `force=True` therefore lets the entry point that is actually
running win.

`level=None` — what every caller passes — resolves **`LOG_LEVEL`**; an explicit level
still wins, so the parameter keeps the meaning it had. An unparseable value raises rather
than falling back, matching `ChatScript`'s fail-at-startup stance: a silently ignored
logging configuration is the failure this module exists to prevent.

`resolve_log_level()` reads `os.environ` first and then `.env` **directly**, via
`dotenv_values`. That second lookup is load-bearing: every entry point calls
`configure_logging()` *before* `load_dotenv()`, and in six of the seven workers
`load_dotenv()` lives inside `subscribe()` rather than `main()`. Reading only
`os.environ` would make a `.env` `LOG_LEVEL` work under Compose (which injects `env_file`
into the process environment) and silently do nothing under `uv run`. `dotenv_values` is
read-only and puts nothing into `os.environ`, so no other variable's resolution order
moves. Full rules in [application logging](/logging.md).

## `repositories/`

Modules of async functions, one per entity — the data-access layer. Fully described in
[repositories](/data-model/repositories.md), including the `_protocols.py` injection
seam and `session.append_history`, the single-statement append that replaced a
read-modify-write on the `sessions.history` column.

## `search/`

`shared/search/rrf.py` provides `rrf_fuse_scored(rankings, k=DEFAULT_RRF_K) ->
list[tuple[UUID, float]]` — a pure, stateless reciprocal rank fusion (`Σ 1/(k +
rank_i)`) that keeps the fused score and takes arbitrarily many rankings, and
`rrf_fuse(rankings, k=DEFAULT_RRF_K) -> list[UUID]`, a thin wrapper dropping the score.
`DEFAULT_RRF_K = 60` is the named damping constant both use by default. Consumed by the
[retrieval agent](/retrieval/chat-agent.md) (`rrf_fuse`) and [deterministic
search](/retrieval/deterministic-search.md) (`rrf_fuse_scored`, which is what lets an
unbounded number of query-expansion variants fuse through the same call as the two
search arms).

`shared/search/filters.py` provides `is_empty_filter(document_filter: DocumentFilter) ->
bool`, derived via `model_dump(exclude_defaults=True)` rather than enumerating fields by
hand, so a `DocumentFilter` field added later cannot silently go unconsidered. The
search service calls it to decide whether a candidate-narrowing query is worth making at
all.

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
`get_url`. `LocalStorageBackend` (under `LOCAL_STORAGE_PATH`, default `./data`) and
`GCSStorageBackend` (wraps `google-cloud-storage`, needs `GCS_BUCKET`).
`create_storage_backend(settings)` lazy-imports GCS libs. Optional dep:
`uv add 'shared[gcs]'`.

`LOCAL_STORAGE_PATH` is the storage **root** every stored key hangs off, not a
PDF-specific directory — every key, whatever it prefixes, is joined onto this path.
`shared/storage/keys.py` provides `document_pdf_key(document_id) -> str` —
`documents/{id}/original.pdf`. It replaces the same literal template that used to be
duplicated in the [download](/pipeline/download.md) and [parse](/pipeline/parse.md)
workers and in `api/services/answerer.py`; all three, plus the new [PDF
endpoint](/api/document-pdf.md), now call the one helper, since the layout is a contract
shared across packages rather than any one caller's detail. `StorageBackend` carries
PDFs only now — [LLM traces](/observability.md) are written directly to disk by `ai`'s
`FileTraceRecorder`, under `LLM_TRACE_KEY_PREFIX` (`llm-traces`, default) beneath the
same `LOCAL_STORAGE_PATH` root, but never through `store()`.

### Why it is only a blob store

The Protocol is deliberately five methods wide. It carries no notion of appending, of
JSON, or of a record — a key maps to a blob of bytes and nothing more, so the two
backends have no behaviour to diverge on and a third would have nothing extra to
implement.

LLM trace capture used to be the pressure pushing the other way, when it went through
this Protocol and wanted an append-style stream. That pressure is gone now that traces
bypass `StorageBackend` entirely and write their own files — see [LLM
Observability](/observability.md) for the layout and the trade that write makes.

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
