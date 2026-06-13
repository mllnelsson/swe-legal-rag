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
  llm-core/          — standalone, project-agnostic LLM abstraction (Provider Protocol, config, service layer, Gemini impl)
  ai/                — project-specific LLM logic: prompt templates, domain DTOs, query decomposition, synthesis, embeddings
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
llm-core        ← standalone, zero dependency on shared; depends only on pydantic, pydantic-settings, google-genai
ai              ← depends on shared + llm-core; depended on by api + relevant workers
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

## LLM Core Package (`packages/llm-core/`)

Standalone, project-agnostic LLM abstraction. Zero dependency on `shared` — fully reusable across projects.

- **`_types.py`:** Frozen dataclasses: `Message`, `ToolCall`, `ToolDefinition`, `LLMResponse`, `StreamChunk`, `Role` (StrEnum).
- **`_exceptions.py`:** `LLMError` base, `ProviderError`, `ToolExecutionError`, `MaxIterationsError`.
- **`_protocol.py`:** `LLMProvider` Protocol (`@runtime_checkable`) with `generate()` and `generate_stream()`. Providers do one round-trip; tool-call loop is in the service layer.
- **`_config.py`:** `LLMConfig(BaseSettings)` reading `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `GEMINI_API_KEY`. `create_provider()` factory with lazy-import dispatch.
- **`providers/gemini.py`:** Gemini implementation using `google-genai` SDK (the new unified SDK, not deprecated `google-generativeai`).
- **`_service.py`:** Higher-level API: `generate()`, `generate_structured()`, `generate_stream()`, `tool_loop()` with optional callbacks.

## AI Package (`packages/ai/`)

Project-specific LLM logic that consumes `llm-core`. Handles domain concerns.

- **Query decomposition & synthesis:** Uses `llm-core` service layer for Gemini calls.
- **Metadata & entity extraction:** Domain-specific orchestration on top of `llm-core`.
- **Embedding interface:** Chunk embedding generation. Model-swappable via config.
- **Prompt templates:** Centralized, versioned. Keeps prompt engineering out of business logic.

### Domain DTOs (`ai/dtos.py`)

Pydantic v2 DTOs for every LLM use case. All models are `frozen=True`.

| Domain | Request | Result |
|---|---|---|
| Query decomposition | `DecomposeRequest` | `DecomposeResult` (with `DateFilter`) |
| Answer synthesis | `SynthesizeRequest` (with `ChunkContext`) | `SourceCitation` |
| Metadata extraction | `MetadataRequest` | `MetadataResult` |
| Entity & reference extraction | `EntityRequest` | `EntityResult` (with `ExtractedEntity`, `ExtractedReference`) |
| Summarization | `SummarizeRequest` | `SummarizeResult` |
| Embedding | `EmbedRequest` | `EmbedResult` |

### Embedding Abstraction (`ai/embedding.py`)

`EmbeddingProvider` is a `@runtime_checkable` Protocol with one method: `async embed(texts) -> list[list[float]]`.

`EmbeddingConfig(BaseSettings)` reads `EMBEDDING_PROVIDER` (default `"local"`) and `EMBEDDING_MODEL` (default `"intfloat/multilingual-e5-base"`).

`create_embedding_provider(config=None) -> EmbeddingProvider` is the factory. It lazy-imports the concrete provider class so the heavy ML library (sentence-transformers) is only loaded when the local provider is actually requested.

**Dimension constraint (locked 2026-06-11):** The default model `intfloat/multilingual-e5-base` produces 768-dim vectors, which matches `shared.config.EMBEDDING_DIMENSION` (default `768`) and the `chunks.embedding` column size baked into migrations. `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` must always change together: update both env vars and provide a new migration that recreates the `chunks.embedding` column at the new dimension.

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

## Crawl Worker (`packages/worker-crawl/`)

One-shot pipeline entry point. Scrapes an HTML page for PDF links, deduplicates against the documents table, and enqueues download tasks.

### Module layout

| Module | Role |
|---|---|
| `config.py` | `CrawlSettings(BaseSettings)` — reads `CRAWL_SOURCE_URL` (required), `CRAWL_REQUEST_TIMEOUT` (default 30s), `CRAWL_TOPIC` (default `"download"`). `get_crawl_settings()` is `@lru_cache`. |
| `client.py` | `CrawlClient` — synchronous HTTP scraper. `fetch_pdf_urls(source_url) -> list[str]` GETs the page with `httpx.Client`, parses HTML with `BeautifulSoup`, extracts `<a href="*.pdf">` links, resolves to absolute URLs, and deduplicates order-preservingly with `dict.fromkeys()`. |
| `service.py` | `CrawlService` + `CrawlResult` — orchestration. Constructor takes `session`, `document_repo`, `task_repo`, `queue_publisher`, `client`, `source_url`, `topic`. Async `run()` method processes each URL, creates `Document` + two `Task` rows (crawl:completed, download:pending), commits, then publishes. |
| `__main__.py` | Entry point. Loads `.env`, wires all dependencies, runs `asyncio.run(_run())`, logs `CrawlResult`. |

### Deduplication and idempotency

`get_by_source_url()` is checked before creating a document. If the row exists, the URL is skipped. On race conditions (concurrent crawl runs), `IntegrityError` on `documents.source_url` unique constraint is caught per-URL — the session is rolled back and the URL is counted as skipped.

### Transaction ordering (sync queue)

`CrawlService.run()` calls `await session.commit()` per document BEFORE publishing to the queue. This is required because `QUEUE_BACKEND=sync` dispatches inline — the download handler opens its own session and must see the document as committed. For `pubsub`, the commit still happens before publish, ensuring rows are durable on the DB before any async consumer can act on the message.

### Error handling

Per-URL errors (HTTP failures, unexpected DB errors) are caught, logged as warnings, and the session is rolled back so the next URL can proceed. The crawl never aborts early on a single bad URL.

## Download Worker (`packages/worker-download/`)

Long-running subscriber. Consumes document IDs from the download topic, fetches PDFs, stores them via the storage backend, updates the document record, and enqueues parse tasks.

### Module layout

| Module | Role |
|---|---|
| `config.py` | `DownloadSettings(BaseSettings)` — reads `DOWNLOAD_REQUEST_TIMEOUT` (default 60s), `DOWNLOAD_TOPIC` (default `"download"`), `DOWNLOAD_NEXT_TOPIC` (default `"parse"`), `DOWNLOAD_MAX_RETRIES` (default 3), `DOWNLOAD_RATE_LIMIT_DELAY` (default 0.5s). `get_download_settings()` is `@lru_cache`. |
| `service.py` | `DownloadService` + module-level `_download_pdf()` function — orchestration. Constructor takes `session`, `document_repo`, `task_repo`, `storage`, `queue_publisher`, and config params. Async `handle_message()` method handles one `QueueMessage`. |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, registers handler via `subscriber.subscribe()`, installs signal handlers, calls `subscriber.start()`. The handler wraps `asyncio.run()` around the async service method so it works with the sync `QueueSubscriber` protocol. |

### Task checkpointing

Each message transitions the task through: `pending → processing → completed | failed`. The processing status is committed immediately after it is set so it is durable before any download I/O begins.

### Session management

Each queued message gets its own `AsyncSession` via `get_async_session()` in the `__main__.py` handler closure. The session is also passed into `DownloadService` to give it explicit commit control (required to commit before publishing to the parse topic, same pattern as crawl worker).

### Download with retry

`_download_pdf(url, timeout, max_retries) -> bytes` is a module-level function (not a method). It creates an `httpx.Client`, attempts up to `max_retries` times, applies exponential backoff (`2**attempt` seconds) between retries. HTTP 4xx responses raise immediately (not retryable). HTTP 5xx, connection errors, and timeouts are retried.

### Transaction ordering (sync queue)

`handle_message()` calls `await session.commit()` BEFORE publishing to the parse topic. This ensures document and parse-task rows are visible to any subscriber that opens a new session (required for `QUEUE_BACKEND=sync` inline dispatch, same as crawl worker).

### Idempotency

Multiple guard layers: (1) task status check — if already `completed`, skip; (2) `document.gcs_uri` check — if already set, skip download but still create parse task and publish; (3) storage `store()` is overwrite-safe (same key → same result); (4) `(document_id, step)` unique constraint prevents duplicate task creation.

### Error handling

Per-message errors are caught in `handle_message()`. On failure: session is rolled back, task is marked `failed` with the error message committed in a fresh transaction, and the error is logged. The exception is not re-raised — one failed message does not affect others. A 0.5s rate-limit sleep follows each successful download.

## Parse Worker (`packages/worker-parse/`)

Long-running subscriber. Consumes parse tasks from the parse topic, retrieves the stored PDF bytes from the storage backend, extracts text using pypdfium2, stores the text in `documents.raw_text`, and enqueues metadata extraction tasks.

### Module layout

| Module | Role |
|---|---|
| `config.py` | `ParseSettings(BaseSettings)` — reads `PARSE_TOPIC` (default `"parse"`), `PARSE_NEXT_TOPIC` (default `"metadata"`). `get_parse_settings()` is `@lru_cache`. |
| `parser.py` | `Parser` Protocol + `parse_pdf_with_pypdfium2()` function. The protocol decouples the service from the concrete PDF library. `ParseError` is the domain exception for parse failures. |
| `service.py` | `process_parse()` async function — orchestration using functional dependency injection (all deps as parameters). |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, registers handler via `subscriber.subscribe()`, installs signal handlers, calls `subscriber.start()`. |

### Parser abstraction

`Parser` is a `typing.Protocol` with a single `__call__(pdf_bytes: bytes) -> str` signature. Any function with this signature satisfies the protocol without inheritance. The concrete `parse_pdf_with_pypdfium2` function:
- Loads the PDF from bytes using `pypdfium2.PdfDocument(pdf_bytes)`
- Iterates pages, extracts text via `page.get_textpage().get_text_range()`
- Joins page texts with `"\n\n---\n\n"` separators
- Wraps pypdfium2 exceptions in `ParseError`

`pypdfium2` uses the Apache 2.0 license (permissive), unlike PyMuPDF/pymupdf4llm which is AGPL.

### Service layer (functional DI)

`process_parse(document_id, task_id, storage, document_repo, task_repo, queue_publisher, parser, session, next_topic)` is a module-level async function. All dependencies are passed as arguments — no global state, no class instance. The `__main__.py` handler closure captures the shared infrastructure objects (storage, publisher) and creates per-message repos.

Storage retrieval uses the deterministic key `documents/{document_id}/original.pdf`, which matches the key the download worker used when storing the PDF.

### Task checkpointing

Each message transitions the task through: `pending → processing → completed | failed`. The processing status is committed immediately after it is set so it is durable before PDF I/O begins.

### Transaction ordering

`process_parse()` calls `await session.commit()` BEFORE publishing to the metadata topic, following the commit-before-publish invariant shared by all workers.

### Idempotency and error handling

- If the task is already `completed` or not found, the message is skipped.
- If `document.gcs_uri` is `None`, the task is marked `failed` (PDF not yet stored).
- On any exception during parsing or storage retrieval: session is rolled back, task is marked `failed` with the error message, then logged.

## Metadata Worker (`packages/worker-metadata/`)

Long-running subscriber. Consumes metadata tasks from the metadata topic, extracts structured metadata from `documents.raw_text` using rule-based patterns first and LLM fallback for missing fields, updates the document record, and enqueues extract tasks.

### Module layout

| Module | Role |
|---|---|
| `config.py` | `MetadataSettings(BaseSettings)` — reads `METADATA_TOPIC` (default `"metadata"`), `METADATA_NEXT_TOPIC` (default `"extract"`). `get_metadata_settings()` is `@lru_cache`. |
| `patterns.py` | `MetadataResult` dataclass + per-field pure extraction functions + combining function `extract_metadata_rule_based()` + `is_complete()` helper. |
| `service.py` | `process_metadata()` async function — orchestration using functional DI (all deps as parameters). |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, defines `_llm_extractor` closure, registers handler, installs signal handlers, calls `subscriber.start()`. |

### Extraction strategy

Two-stage extraction with rule-based first, LLM fallback only for missing fields:

1. **Rule-based (`patterns.py`):** Per-field pure functions using `re` patterns for Swedish legal document formats.
   - `extract_case_number`: Matches `Dnr`, `Diarienummer`, `ÖN`, or bare `YYYY-NNN` patterns.
   - `extract_decision_date`: Tries ISO (`2023-01-15`), Swedish textual (`den 15 januari 2023`), Swedish abbreviated (`15 jan 2023`). Maps Swedish month names to month numbers.
   - `extract_decision_outcome`: Searches near document end for `bifaller/avslår/avvisar överklagandet` and returns the surrounding sentence.
   - `extract_category`: Matches `Ärende:`, `Ämne:`, or `Kategori:` header lines.
2. **LLM fallback (via `ai` package):** Only invoked when rule-based extraction leaves fields `None`. `extract_metadata_llm(raw_text, missing_fields)` in `packages/ai/src/ai/_metadata.py` calls `llm_core.generate_structured()` with a `_LLMFields` Pydantic schema and returns `MetadataLLMResult`.
3. **Merge:** Rule-based values always win. LLM values only fill fields that remain `None` after rule-based extraction.

All metadata fields are freeform `VARCHAR` — no enum constraints. Missing metadata (all fields `None`) is a valid outcome; the task still completes.

### AI Package (`packages/ai/`) — current contents

- **`dtos.py`:** All domain DTOs (see AI Package section above). Imported directly by service functions and consumers.
- **`embedding.py`:** `EmbeddingProvider` protocol, `EmbeddingConfig`, `create_embedding_provider` factory.
- **`_local_embedding.py`:** `LocalEmbeddingProvider` using `sentence-transformers`. Lazy-imported by the factory; not part of the public API.
- **`_metadata.py`:** `extract_metadata_llm(raw_text, missing_fields) -> MetadataLLMResult`. Uses `llm_core.generate_structured()` with a structured Pydantic response. Handles ISO date string → `datetime.date` conversion. Returns `MetadataLLMResult` (Pydantic model with `case_number`, `decision_date`, `decision_outcome`, `category`). _(Will be migrated into the prompts/services structure in a later task.)_
- **`__init__.py`:** Exports `extract_metadata_llm` and `MetadataLLMResult`.

### Service layer (functional DI)

`process_metadata(document_id, task_id, document_repo, task_repo, queue_publisher, rule_extractor, llm_extractor, session, next_topic)` is a module-level async function. `rule_extractor: Callable[[str], MetadataResult]` and `llm_extractor: Callable[[str, list[str]], Awaitable[MetadataResult]]` are injected — the service has no knowledge of the concrete LLM provider.

### Error handling

- LLM failure is non-fatal: logged as warning, extraction continues with partial metadata.
- Only DB errors and unhandled crashes mark the task as `failed`.
- Missing metadata is valid — task completes with `None` fields written to the document.

### Task checkpointing

Each message transitions the task through: `pending → processing → completed | failed`. Processing status committed immediately before I/O begins. Follows the commit-before-publish invariant (session committed before publishing to extract topic).

## Worker Architecture

### Two worker patterns

- **One-shot workers** (e.g., crawl): Run once, process all items, exit. Launched by Cloud Scheduler via Cloud Run Jobs. Entry point calls `asyncio.run()`, logs the result, then exits.
- **Subscriber workers** (e.g., download, parse): Register a queue handler, block on messages. Suitable for Cloud Run triggered by Pub/Sub push. Entry point installs signal handlers and calls `subscriber.start()`.

### Service layer pattern

Workers use dependency injection with no global state. Earlier workers (crawl, download) use a service class with constructor injection. The parse worker (and subsequent workers) use a functional approach: a module-level `process_*` async function that takes all dependencies as parameters. Both patterns are equivalent — the `__main__.py` handler closure captures the shared infrastructure objects and passes them on each call.

### Session-per-message pattern

Subscriber workers create a new `AsyncSession` for each message (via `get_async_session()` in `__main__.py`). The session is passed into the service constructor, giving the service explicit commit control. One failed message does not roll back others.

### Config pattern

Worker-specific settings extend `pydantic_settings.BaseSettings`. Each worker reads its own env vars alongside the shared `Settings`. `@lru_cache` is used for singleton config instances.

### Commit-before-publish invariant

All workers call `await session.commit()` before calling `queue_publisher.publish()`. This ensures that when `QUEUE_BACKEND=sync` dispatches inline (the subscriber opens a new session in-process), the committed rows are visible. The same ordering is correct for Pub/Sub — rows are durable before any async consumer can act on a message.

### Integration test pattern

Integration tests use:
- **Real async `Session`** backed by Docker Postgres
- **Real repos and storage** — verifies the wiring between service, repo, and storage layers
- **Mocked HTTP** only — no actual network calls to source servers
- **`SyncQueueBroker` with recording handler** — captures published messages without triggering downstream workers; avoids `ValueError` from unregistered topics
- **Table truncation before each test** (`TRUNCATE documents CASCADE`) — ensures test isolation even when services commit data

## Design Principles

- **Interface abstraction everywhere:** LLM provider, embedding model, storage backend (GCS/local), queue (Pub/Sub/local) — all swappable via config for local dev and future flexibility.
- **DTOs as boundaries:** Pydantic models define the contract between layers. ORM objects never cross the repo boundary.
- **Workers are thin:** Each worker's service layer does one thing. Complexity lives in `shared` and `ai`.
- **Config over code:** Model selection, provider keys, DB connection, queue config — all environment-driven.
