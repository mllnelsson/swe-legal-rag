# Backend Design Spec: Överklagandenämnden Decision Search Tool

## Tooling

- **uv** — package management and workspace orchestration
- **FastAPI** — API framework
- **SQLAlchemy** — ORM
- **Alembic** — database migrations
- **Pydantic** — DTOs and request/response models

## Repo Structure (uv workspace)

Monorepo with separate packages per concern. Shared code and AI tooling as internal packages.

```
packages/
  shared/            — SQLAlchemy models, Pydantic DTOs, repo layer, DB config, common utils
  ai/                — LLM and embedding abstractions (provider interfaces, prompt templates, model config)
  api/               — FastAPI app, endpoints, service layer for query/retrieval
  worker-crawl/
  worker-download/
  worker-parse/
  worker-metadata/
  worker-extract/      — entity & reference extraction (GraphRAG-lite)
  worker-chunk/
  worker-embed/
alembic/             — migration scripts (root-level, runs against shared.db.Base metadata)
alembic.ini          — Alembic config (sqlalchemy.url set via DATABASE_URL env var in env.py)
docker-compose.yml   — Postgres+pgvector default, MinIO+Redis under "full" profile
docker/init.sql      — enables pgvector extension on first DB creation
```

All packages use src layout (`packages/<name>/src/<python_name>/`) with `py.typed` markers. Python package names use underscores for hyphenated directory names (e.g. `worker-crawl` → `worker_crawl`).

Each worker is its own deployable unit (Cloud Run service), own `pyproject.toml`, depends on `shared`. The `ai` package is consumed by `api` (query decomposition, synthesis), `worker-metadata` (LLM fallback extraction), `worker-extract` (entity & reference extraction), `worker-chunk` (summary generation), and `worker-embed` (embedding generation).

## Package Dependency Graph

```
shared          ← depended on by everything
ai              ← depends on shared (for DTOs), depended on by api + relevant workers
api             ← depends on shared, ai
worker-*        ← depends on shared, some depend on ai
```

## Layered Architecture

```
Model (SQLAlchemy)  →  Repo (queries + ORM→DTO mapping)  →  Service (business logic)  →  Endpoint (HTTP concerns)
```

- **Model:** SQLAlchemy table definitions. Lives in `shared`. Single source of truth for schema, Alembic generates migrations from these.
- **Repo:** Query logic only. Takes and returns Pydantic DTOs — never leaks ORM objects upward. Lives in `shared`.
- **Service:** Business and domain logic. Orchestrates repos, calls `ai` package, handles pipeline logic. Lives in respective package (`api` or worker).
- **Endpoint:** Request parsing, response formatting, HTTP status codes. Thin layer. Lives in `api`.

Workers skip the endpoint layer — they consume from Pub/Sub directly into the service layer.

## AI Package (`packages/ai/`)

Abstracts all LLM and embedding interactions behind provider-agnostic interfaces.

- **LLM interface:** Query decomposition, answer synthesis, metadata extraction (fallback). Provider-swappable (Gemini Flash, Haiku, etc.) via config.
- **Embedding interface:** Chunk embedding generation. Model-swappable (e5-multilingual, Cohere, etc.) via config.
- **Prompt templates:** Centralized, versioned. Keeps prompt engineering out of business logic.
- **Model config:** Model selection, temperature, token limits — all config-driven, no hardcoded values.

## Shared Package Module Layout

The `packages/shared/src/shared/` package is the single source of truth for data and database access.

### `config.py`

Centralized, pydantic-settings-backed configuration for the entire shared package.

| Class | Reads env vars | Purpose |
|---|---|---|
| `DatabaseSettings` | `DATABASE_URL` | Database connection string (required) |
| `StorageSettings` | `STORAGE_BACKEND`, `LOCAL_STORAGE_PATH`, `GCS_BUCKET` | Storage backend config; defaults to `local` |
| `QueueSettings` | `QUEUE_BACKEND`, `PUBSUB_PROJECT_ID` | Queue backend config; defaults to `sync` |
| `Settings` | (composes the above) | Root container; access via `get_settings()` |

`StorageBackendType` (`local`, `gcs`) and `QueueBackendType` (`sync`, `pubsub`) are `StrEnum` types used for exhaustive `match`/`case` dispatch in factories.

Cross-field validators enforce: GCS backend requires `GCS_BUCKET`; Pub/Sub backend requires `PUBSUB_PROJECT_ID`.

`get_settings()` returns a cached singleton (`@lru_cache(maxsize=1)`). In tests, call `get_settings.cache_clear()` between cases.

`EMBEDDING_DIMENSION` (int, default `768`) is also defined here. Imported by the `Chunk` model to configure vector dimension at startup.

### `models/`

SQLAlchemy 2.x models, one file per table. All use `DeclarativeBase` from `models/base.py`. Import all models from `models/__init__.py`.

Key design decisions:
- `chunks.embedding`: `pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSION)` — dimension resolved from env at import time
- `chunks.tsv`: PostgreSQL `GENERATED ALWAYS AS (to_tsvector('swedish', chunk_text)) STORED` — computed at the DB layer via SQLAlchemy `Computed(..., persisted=True)`
- `documents.updated_at`: uses `onupdate=func.now()` for automatic server-side update timestamps

### `dtos/`

Pydantic v2 models for every entity. Pattern per entity:
- `*Create` — input for inserts, omits server-generated fields (id, created_at)
- `*Read` — full record returned by queries, uses `model_config = ConfigDict(from_attributes=True)` for ORM→DTO via `model_validate()`
- `*Update` — partial update, all fields `Optional` (progressive fill pattern)

The repo layer enforces the DTO boundary: ORM objects never escape past the repository.

### `repositories/`

Async repository classes. Each takes an `AsyncSession` constructor argument and exposes entity-specific CRUD methods. All methods accept and return DTOs — never ORM objects.

Notable patterns:
- `DocumentRepository.update`: calls `model_dump(exclude_none=True)` to only update fields provided in the update DTO
- `TaskRepository.update_status`: automatically sets `started_at` when transitioning to `processing`, `completed_at` when transitioning to `completed`/`failed`
- `EntityRepository.upsert`: check-then-insert pattern using the `(name, type)` unique constraint
- `ChunkRepository.bulk_create`: uses `session.add_all()` for efficient batch insert

### `db.py`

Provides two database access paths:

| Function | Purpose |
|---|---|
| `get_engine()` | Returns a cached sync SQLAlchemy `Engine` using `postgresql+psycopg://`. Used by Alembic. |
| `get_session()` | Sync context manager yielding a `Session`. Used for Alembic offline mode. |
| `get_async_session()` | Async context manager yielding an `AsyncSession` with auto commit/rollback. Used by application code. |

`get_engine()` is decorated with `@lru_cache(maxsize=1)` so the same `Engine` instance is returned on every call — connection pool is shared across the process. `pool_pre_ping=True` validates connections before checkout. The `DATABASE_URL` is read from `get_settings().database.database_url` (not `os.environ` directly).

The async engine uses `postgresql+asyncpg://` (asyncpg driver). URL scheme is normalized regardless of its original scheme.

### Async session pattern (dependency injection)

```python
from shared.db import get_async_session

async with get_async_session() as session:
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(doc_id)
```

In FastAPI, wrap `get_async_session` in a dependency. In workers, use it directly in service methods.

### Infrastructure Abstractions

The `config.py`, `storage/`, and `queue/` modules together form the infrastructure abstraction layer. Each concern is represented by a Protocol interface, a set of backend implementations, and a factory function that selects the backend from environment variables. This makes local development and GCP deployment a config change — no code changes required.

### `storage/`

Storage backend abstraction for binary object storage (raw document files, etc.).

| Backend | Class | Description |
|---|---|---|
| `local` | `LocalStorageBackend` | Persists files under `LOCAL_STORAGE_PATH` (default `./storage`) |
| `gcs` | `GCSStorageBackend` | Wraps `google-cloud-storage`; requires `GCS_BUCKET` env var |

`StorageBackend` is a `@runtime_checkable` Protocol with: `store`, `retrieve`, `exists`, `delete`, `get_url`.
`create_storage_backend(settings)` is the factory; uses lazy imports so GCS libs are never loaded when using local backend.
GCS is an optional dependency: `uv add 'shared[gcs]'`.

### `queue/`

Queue abstraction for inter-worker messaging (pipeline fan-out).

| Backend | Classes | Description |
|---|---|---|
| `sync` | `SyncQueuePublisher`, `SyncQueueSubscriber` | In-process; publish directly invokes the registered handler. Ideal for local dev and testing. |
| `pubsub` | `PubSubQueuePublisher`, `PubSubQueueSubscriber` | GCP Pub/Sub via streaming pull; serializes `QueueMessage` as JSON bytes. |

**Key types:**
- `QueueMessage(BaseModel)`: `task_id: UUID`, `document_id: UUID`, `payload: dict` — maps 1:1 to task rows in the DB.
- `QueuePublisher` Protocol: `publish(topic, message) -> None`
- `QueueSubscriber` Protocol: `subscribe(topic, handler)`, `start()`, `shutdown()`

**Sync broker pattern:** `SyncQueueBroker` holds a `dict[topic, handler]`. Publisher and subscriber in the same process must share the same broker instance — `_get_sync_broker()` in `factory.py` provides a module-level singleton for this purpose.

`create_queue_publisher(settings)` and `create_queue_subscriber(settings)` are the factories; backend selected by `QUEUE_BACKEND` env var (`sync` default, `pubsub` for GCP).
Pub/Sub is an optional dependency: `uv add 'shared[pubsub]'`. Both GCS and Pub/Sub together: `uv add 'shared[gcp]'`.

## Design Principles

- **Interface abstraction everywhere:** LLM provider, embedding model, storage backend (GCS/local), queue (Pub/Sub/local) — all swappable via config for local dev and future flexibility.
- **DTOs as boundaries:** Pydantic models define the contract between layers. ORM objects never cross the repo boundary.
- **Workers are thin:** Each worker's service layer does one thing. Complexity lives in `shared` and `ai`.
- **Config over code:** Model selection, provider keys, DB connection, queue config — all environment-driven.
