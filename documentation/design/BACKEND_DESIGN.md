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
- **Prompt templates:** Centralized, versioned in `ai/prompts/`. Keeps prompt engineering out of business logic.

### Prompt Templates (`ai/prompts/`)

`PromptTemplate` is a frozen dataclass with `system_prompt: str`, `user_template: str`, and `render(context: dict) -> list[Message]`. `render()` substitutes variables via `str.format_map(context)` and returns `[Message(SYSTEM, system_prompt), Message(USER, rendered_user)]`.

Five template constants cover all LLM use cases:

| Constant | Output format | User template variables |
|---|---|---|
| `QUERY_DECOMPOSITION` | JSON (`DecomposeResult` schema) | `{question}`, `{conversation_history}` |
| `ANSWER_SYNTHESIS` | Plain Swedish text with case citations | `{question}`, `{chunks}`, `{conversation_history}` |
| `METADATA_EXTRACTION` | JSON (`MetadataResult` schema) | `{raw_text}` |
| `ENTITY_EXTRACTION` | JSON (`EntityResult` schema) | `{raw_text}`, `{case_number}` |
| `DOCUMENT_SUMMARIZATION` | Plain Swedish text | `{raw_text}` |

All JSON-outputting templates embed the exact field schema in their system prompt. All prompts instruct the model to work in Swedish.

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

`EmbeddingConfig(BaseSettings)` reads `EMBEDDING_PROVIDER` (default `"local"`) and `EMBEDDING_MODEL` (default `"intfloat/multilingual-e5-large"`).

`create_embedding_provider(config=None) -> EmbeddingProvider` is the factory. It lazy-imports the concrete provider class so the heavy ML library (sentence-transformers) is only loaded when the local provider is actually requested.

**Dimension constraint:** The default model `intfloat/multilingual-e5-large` produces 1024-dim vectors, which matches `shared.config.EMBEDDING_DIMENSION` (default `1024`) and the `chunks.embedding` column size baked into migrations. `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` must always change together: update both env vars and provide a new migration that recreates the `chunks.embedding` column at the new dimension. See ARCHITECTURE.md §7 for model choice rationale and hosting strategy.

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

`EMBEDDING_DIMENSION` (int, default `1024`) is also defined here. Imported by the `Chunk` model to configure vector dimension at startup.

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

`shared/dtos/search.py` holds two search-specific DTOs that live outside the per-entity pattern: `DocumentFilter` (all-optional filter criteria consumed by `SearchRepository`) and `ChunkSearchResult` (chunk id + document_id + text + index + raw score, returned by both `vector_search` and `text_search`). The `ai` package maps `ai.dtos.DecomposeResult` onto `DocumentFilter` in the `api` service layer — `shared` must not import from `ai`.

### `repositories/`

Async repository classes. Each takes an `AsyncSession` constructor argument and exposes entity-specific CRUD methods. All methods accept and return DTOs — never ORM objects.

Notable patterns:
- `DocumentRepository.update`: calls `model_dump(exclude_none=True)` to only update fields provided in the update DTO
- `DocumentRepository.get_by_case_number`: looks up a document by `case_number` field
- `TaskRepository.update_status`: automatically sets `started_at` when transitioning to `processing`, `completed_at` when transitioning to `completed`/`failed`
- `EntityRepository.upsert`: check-then-insert pattern using the `(name, type)` unique constraint
- `DocumentEntityRepository.upsert`: check-then-insert; upgrades `relevance` from `mentioned` to `primary` if re-seen as primary
- `DocumentReferenceRepository.upsert`: check-then-insert; idempotent insert using `(source_document_id, target_document_id)` composite PK
- `UnresolvedReferenceRepository.upsert/get_by_target_case_number/delete`: manages unresolved cross-references pending reconciliation
- `ChunkRepository.bulk_create`: uses `session.add_all()` for efficient batch insert
- `ChunkRepository.update_embeddings(updates: list[tuple[UUID, list[float]]])`: bulk UPDATE setting `embedding` column per chunk; does not touch `tsv` (GENERATED ALWAYS computed column)
- `ChunkRepository.vector_search(embedding, document_ids, limit)`: pgvector cosine distance ordering; filters to candidate `document_ids` when provided; excludes NULL embeddings
- `ChunkRepository.text_search(query, document_ids, limit)`: `websearch_to_tsquery('swedish', query)` against `tsv` column ranked by `ts_rank`; filters to candidate `document_ids` when provided
- `SearchRepository.find_candidate_documents(filter: DocumentFilter) -> list[UUID]`: narrows corpus before semantic search via metadata WHERE-conditions, EXISTS subqueries through `document_entities`→`entities`, and `document_references` traversal in both directions (cites + cited-by); empty filter returns all document IDs with `raw_text`

### `search/`

`packages/shared/src/shared/search/rrf.py` provides `rrf_fuse(rankings: list[list[UUID]], k: int = 60) -> list[UUID]` — a pure, stateless reciprocal rank fusion function. Score for each document is `Σ 1/(k + rank_i)` over all rankings in which it appears. Returns IDs sorted by descending score. No DB or I/O. Consumed by the `api` service layer to combine vector and text search results.

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
2. **LLM fallback (via `ai` package):** Only invoked when rule-based extraction leaves fields `None`. The `_llm_extractor` closure in `__main__.py` calls `ai.services.extract_metadata(raw_text)`, which renders the `METADATA_EXTRACTION` template and calls `llm_core.generate_structured()` returning `ai.dtos.MetadataResult`. The closure converts `decision_date` from ISO string to `datetime.date` before returning `worker_metadata.patterns.MetadataResult`.
3. **Merge:** Rule-based values always win. LLM values only fill fields that remain `None` after rule-based extraction.

All metadata fields are freeform `VARCHAR` — no enum constraints. Missing metadata (all fields `None`) is a valid outcome; the task still completes.

### AI Package (`packages/ai/`) — module layout

| Module | Role |
|---|---|
| `dtos.py` | All domain DTOs — frozen Pydantic v2 models for every LLM use case |
| `services.py` | Five async service functions (see table below) |
| `embedding.py` | `EmbeddingProvider` Protocol, `EmbeddingConfig`, `create_embedding_provider` factory |
| `providers/local_embeddings.py` | `LocalEmbeddingProvider` using `sentence-transformers` |
| `prompts/_renderer.py` | `PromptTemplate` frozen dataclass |
| `prompts/_templates.py` | Five template constants (see Prompt Templates section above) |
| `__init__.py` | Public API — exports all service functions, embedding types, and DTOs |

### Service Functions (`ai/services.py`)

| Function | Signature | LLM call |
|---|---|---|
| `decompose_query` | `async (question: str, conversation_history: list[dict] \| None = None, *, provider=None) -> DecomposeResult` | `generate_structured` |
| `extract_metadata` | `async (raw_text: str, *, provider=None) -> MetadataResult` | `generate_structured` |
| `extract_entities` | `async (raw_text: str, case_number: str \| None = None, *, provider=None) -> EntityResult` | `generate_structured` |
| `summarize_document` | `async (raw_text: str, *, provider=None) -> SummarizeResult` | `generate` |
| `synthesize_answer` | `async (request: SynthesizeRequest, *, provider=None) -> AsyncIterator[str]` | `generate_stream` |

`synthesize_answer` is an async generator (SSE critical path): formats chunks with `[Mål {case_number}]` prefixes, renders `ANSWER_SYNTHESIS`, and yields tokens directly without buffering.

### DTO Contracts (`ai/dtos.py`)

All DTOs are `frozen=True` Pydantic v2 models. Consumers depend on these — do not remove or rename fields.

| Domain | Request type | Result type |
|---|---|---|
| Query decomposition | `DecomposeRequest` | `DecomposeResult` (with `DateFilter`) |
| Answer synthesis | `SynthesizeRequest` (with `ChunkContext`) | streaming `str` tokens; `SourceCitation` for UI |
| Metadata extraction | `MetadataRequest` | `MetadataResult` |
| Entity & reference extraction | `EntityRequest` | `EntityResult` (with `ExtractedEntity(name, type, relevance)`, `ExtractedReference(case_number, reference_context)`) |
| Summarization | `SummarizeRequest` | `SummarizeResult` |
| Embedding | `EmbedRequest` | `EmbedResult` |

`ChunkContext.score: float` is a required field (no default).

### Config Variables

| Var | Default | Used by |
|---|---|---|
| `EMBEDDING_PROVIDER` | `"local"` | `EmbeddingConfig` — selects the provider class |
| `EMBEDDING_MODEL` | `"intfloat/multilingual-e5-large"` | `EmbeddingConfig` — passed to `LocalEmbeddingProvider` |
| `LLM_PROVIDER` | (see llm-core) | `LLMConfig` in `llm-core` |
| `LLM_MODEL` | (see llm-core) | `LLMConfig` in `llm-core` |
| `LLM_TEMPERATURE` | (see llm-core) | `LLMConfig` in `llm-core` |
| `LLM_MAX_TOKENS` | (see llm-core) | `LLMConfig` in `llm-core` |
| `GEMINI_API_KEY` | (required for Gemini) | `LLMConfig` in `llm-core` |

### llm-core / ai Package Boundary

These two packages have distinct responsibilities and must not be confused:

- **`llm-core`** — generic, project-agnostic LLM abstraction. Knows nothing about this domain. Provides: `Message`, `LLMProvider` Protocol, `LLMConfig`, `generate()`, `generate_structured()`, `generate_stream()`, `tool_loop()`. Zero dependency on `shared`.
- **`ai`** — project-specific LLM logic. Knows about Swedish legal documents. Provides: domain DTOs, prompt templates, service functions, embedding abstraction. Depends on both `shared` and `llm-core`.

**Rule:** `ai` calls `llm-core` — never the SDK (google-genai) directly. New use cases go in `ai`, not in `llm-core`.

### Adding a New LLM Use Case

1. **Add DTOs** to `ai/dtos.py`: `YourRequest(BaseModel, frozen=True)` and `YourResult(BaseModel, frozen=True)`.
2. **Add a template** to `ai/prompts/_templates.py`: a `PromptTemplate` constant with `system_prompt` (never substituted) and `user_template` (substituted via `str.format_map`).
3. **Add a service function** to `ai/services.py`:
   ```python
   async def your_function(raw_text: str, *, provider: LLMProvider | None = None) -> YourResult:
       messages = YOUR_TEMPLATE.render({"raw_text": raw_text})
       return await generate_structured(messages, YourResult, provider=provider)  # type: ignore[return-value]
   ```
4. **Export from `__init__.py`**: add to imports and `__all__`.
5. **Write a unit test** in `packages/ai/tests/unit/` — mock `ai.services.generate_structured`.

### Service layer (functional DI)

`process_metadata(document_id, task_id, document_repo, task_repo, queue_publisher, rule_extractor, llm_extractor, session, next_topic)` is a module-level async function. `rule_extractor: Callable[[str], MetadataResult]` and `llm_extractor: Callable[[str, list[str]], Awaitable[MetadataResult]]` are injected — the service has no knowledge of the concrete LLM provider.

### Error handling

- LLM failure is non-fatal: logged as warning, extraction continues with partial metadata.
- Only DB errors and unhandled crashes mark the task as `failed`.
- Missing metadata is valid — task completes with `None` fields written to the document.

### Task checkpointing

Each message transitions the task through: `pending → processing → completed | failed`. Processing status committed immediately before I/O begins. Follows the commit-before-publish invariant (session committed before publishing to extract topic).

## Extract Worker (`packages/worker-extract/`)

Long-running subscriber. Consumes extract tasks from the extract topic, extracts entities and cross-references from `documents.raw_text`, stores them in `entities`, `document_entities`, `document_references`, and `unresolved_references`, and enqueues chunk tasks.

### Module layout

| Module | Role |
|---|---|
| `models.py` | `EntityType` and `Relevance` StrEnums; `ExtractedEntity`, `ExtractedReference`, `ExtractionResult` Pydantic DTOs |
| `parsing.py` | `parse_llm_response(raw_json) -> ExtractionResult` — parses raw LLM JSON, validates types/relevance, normalizes names (lowercase, strip whitespace), deduplicates by (name, type) keeping highest relevance |
| `extractors/base.py` | `ExtractionStrategy` Protocol: `async extract(document_text, case_number=None) -> ExtractionResult` |
| `extractors/rule_based.py` | Pure functions + `RuleBasedStrategy` — regex-based extraction; handles Swedish inflections |
| `extractors/llm.py` | `LLMStrategy` — delegates to `ai.extract_entities()`, maps `ai.dtos.EntityResult` to `ExtractionResult` |
| `extractors/factory.py` | `ExtractStrategyMode` StrEnum; `get_extraction_strategy()` factory; `_FallbackStrategy` and merge logic |
| `services/entity_service.py` | `normalize_entity_name()`, `persist_entities()` — normalizes, deduplicates, and upserts entities to `entities`+`document_entities` |
| `services/reference_service.py` | `process_references()`, `reconcile_references()` — routes references to `document_references` or `unresolved_references`; reconciles lazy-unresolved refs |
| `services/extraction_service.py` | `process_extraction()` — checkpointing wrapper: validates doc, runs strategy, persists, publishes to chunk topic |
| `config.py` | `ExtractSettings(BaseSettings)` — reads `EXTRACT_TOPIC`, `EXTRACT_NEXT_TOPIC` |
| `__main__.py` | Entry point. Loads `.env`, wires repos, registers handler via `subscriber.subscribe()`, installs signal handlers, calls `subscriber.start()` |

### Extraction strategies

Three strategies, selected by the `EXTRACT_STRATEGY` env var (default: `rule_based_with_llm_fallback`):

| Value | Behaviour |
|---|---|
| `rule_based` | Only regex-based extraction — fast, no LLM cost |
| `llm` | Only LLM extraction via `ai.extract_entities()` |
| `rule_based_with_llm_fallback` | Rule-based first; LLM runs only when result is incomplete (zero entities or entity count below threshold for document length); results are merged with rule-based winning deduplication |

### Rule-based extraction (`extractors/rule_based.py`)

Pure functions, no I/O:
- **Regulations:** Matches `kyrkoordningen X kap. Y §`, `kyrkoordningen kapitel X`, `KO X:Y`
- **Parishes:** Matches `X församling`, `X stift`, `församlingen i X`
- **Roles:** Exact-word lookup from known set (`kyrkoherde`, `kyrkoråd`, `kyrkofullmäktige`, `biskop`, `domkapitel`, `kontraktsprost`, `domprost`, `stiftsstyrelse`) — handles Swedish definite/genitive suffixes (`-en`, `-et`, `-s`, `-ns`, `-ts`, `-n`, `-t`, `-r`)
- **Legal concepts:** Exact-word lookup from known set (`överklagande`, `behörighet`, `jäv`, `verkställighet`, `tjänstetillsättning`, `överklaganderätt`, `tjänsteförseelse`, `disciplinärende`) — same inflection handling
- **Cross-references:** `_CASE_REF_RE` matches `ÖN YYYY-NNNN` with optional `dnr` prefix; extracts surrounding sentence as `reference_context`
- **Relevance heuristic:** Entities in the latter 60% of the document are `primary`; earlier occurrences are `mentioned`

Entity names are normalized to lowercase. Each type of entity is deduplicated by (name) within the extraction run.

### Entity persistence (`services/entity_service.py`)

`normalize_entity_name(name)` lowercases and collapses whitespace. `persist_entities(entity_repo, doc_entity_repo, document_id, entities)`:
1. Deduplicates within the batch (primary relevance wins over mentioned for same name+type key)
2. Upserts each entity into `entities` via `EntityRepository.upsert` (check-then-insert; unique on `name, type`)
3. Upserts the `document_entities` row via `DocumentEntityRepository.upsert` — upgrades relevance from `mentioned` to `primary` if the entity is re-seen as primary

### Reference processing (`services/reference_service.py`)

`process_references(doc_repo, ref_repo, unresolved_repo, source_document_id, source_case_number, references)`:
- Skips self-references (where `ref.case_number == source_case_number`)
- For each remaining reference: looks up `case_number` in `documents.case_number`
  - If found → upserts into `document_references` (idempotent)
  - If not found → upserts into `unresolved_references` (idempotent via `unique(source_document_id, target_case_number)`)

`reconcile_references(unresolved_repo, ref_repo, document_id, case_number) -> int`:
- Called after extraction for the current document's own `case_number`
- Queries `unresolved_references` where `target_case_number` matches
- For each match: creates a `document_references` row, deletes the `unresolved_references` row
- Returns the count of resolved references

### Unresolved references (lazy cross-reference resolution)

Cross-references where the target document is not yet in the corpus are stored in `unresolved_references` rather than dropped. The table has a unique constraint on `(source_document_id, target_case_number)` so the same reference can't be stored twice. When the target document is later ingested and its `case_number` is known, `reconcile_references()` converts the unresolved rows to proper `document_references` rows.

### `process_extraction()` (functional DI, same pattern as `process_metadata`)

`process_extraction(document_id, task_id, document_repo, task_repo, entity_repo, doc_entity_repo, ref_repo, unresolved_repo, queue_publisher, session, next_topic)`:
1. Gets task; skips if already `completed`; marks `processing` and commits
2. Validates document exists and has `raw_text`; marks `failed` if not
3. Runs extraction strategy, persists entities, processes references, reconciles
4. Creates chunk task, commits, publishes to next topic, marks `completed`
5. On any exception: rolls back, marks `failed` with error message; does not re-raise

### Worker-extract DTOs (`models.py`)

| Type | Fields |
|---|---|
| `EntityType` (StrEnum) | `legal_concept`, `role`, `parish`, `regulation` |
| `Relevance` (StrEnum) | `primary`, `mentioned` |
| `ExtractedEntity` | `name: str`, `type: EntityType`, `relevance: Relevance` |
| `ExtractedReference` | `case_number: str`, `reference_context: str` |
| `ExtractionResult` | `entities: list[ExtractedEntity]`, `references: list[ExtractedReference]` |

### Config variables

| Var | Default | Used by |
|---|---|---|
| `EXTRACT_STRATEGY` | `rule_based_with_llm_fallback` | `get_extraction_strategy()` — selects extraction approach |
| `EXTRACT_TOPIC` | `extract` | `ExtractSettings` — subscribe topic |
| `EXTRACT_NEXT_TOPIC` | `chunk` | `ExtractSettings` — topic published to on success |

## Chunk Worker (`packages/worker-chunk/`)

Long-running subscriber. Consumes chunk tasks from the chunk topic, generates a document-level summary via LLM, splits `documents.raw_text` into overlapping token-bounded chunks with the summary prepended (contextual retrieval), stores them in `chunks`, and enqueues embed tasks.

### Module layout

| Module | Role |
|---|---|
| `config.py` | `ChunkSettings(BaseSettings)` — reads `CHUNK_TOPIC` (default `"chunk"`), `CHUNK_NEXT_TOPIC` (default `"embed"`). `get_chunk_settings()` is `@lru_cache`. |
| `chunker.py` | Pure functions: `split_into_chunks()` (sentence-aware, tiktoken-based) and `build_contextual_text()` |
| `service.py` | `process_chunking()` async function — orchestration using functional DI (all deps as parameters) |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, registers handler, installs signal handlers, calls `subscriber.start()` |

### Chunking algorithm (`chunker.py`)

`split_into_chunks(text, max_tokens=500, overlap_tokens=50, encoding_name="cl100k_base") -> list[str]`:

1. Returns `[]` for empty/whitespace-only text
2. Splits text into sentences by sentence-ending punctuation (`[.!?]` followed by whitespace) or blank lines (`\n{2,}`)
3. Greedily accumulates sentences until adding the next would exceed `max_tokens`
4. When full: emits chunk as `" ".join(current_sentences)`, then rewinds — retains trailing sentences totalling ≤ `overlap_tokens` as the start of the next chunk
5. Single sentences exceeding `max_tokens` are emitted as their own chunk with no overlap

**Key decisions:**
- **tiktoken cl100k_base** — used purely as a token-counting ruler, not related to the embedding model. `cl100k_base` (GPT-4's tokenizer) undercounts relative to the e5 WordPiece tokenizer for Swedish text; the ~500 token budget provides headroom so chunks stay within the embedding model's 512-token max sequence length. See ARCHITECTURE.md §7 for details.
- **Sentence-aware** — never splits mid-sentence; Swedish legal text has clear `.` boundaries
- **50-token overlap** — last N sentences of the previous chunk repeat at the start of the next, preserving cross-boundary context for embedding

`build_contextual_text(summary, chunk_text) -> str` produces `"{summary}\n\n---\n\n{chunk_text}"`. The summary is prepended to every chunk's `contextual_text` field — only `contextual_text` is embedded, never shown to users directly. `chunk_text` remains the raw extracted text.

### `process_chunking()` (functional DI)

`process_chunking(document_id, task_id, document_repo, chunk_repo, task_repo, queue_publisher, session, next_topic)`:

1. Gets task; skips if already `completed`; marks `processing` and commits
2. Validates document exists and has `raw_text`; marks `failed` if not
3. Calls `ai.summarize_document(raw_text)` — Swedish legal summary in 2–3 sentences
4. Stores summary: `document_repo.update(document_id, DocumentUpdate(summary=summary))`
5. Splits raw text into chunks via `split_into_chunks()`
6. Deletes existing chunks (`chunk_repo.delete_by_document_id`) for idempotency
7. Bulk inserts `ChunkCreate` DTOs with both `chunk_text` and `contextual_text = build_contextual_text(summary, chunk_text)`
8. Creates embed task, commits, publishes to embed topic
9. Marks chunk task `completed`; on any exception: rolls back, marks `failed` with error message, re-raises

Empty `raw_text` (not `None`) produces zero chunks — the task still completes and publishes to embed.

### Config variables

| Var | Default | Used by |
|---|---|---|
| `CHUNK_TOPIC` | `chunk` | `ChunkSettings` — subscribe topic |
| `CHUNK_NEXT_TOPIC` | `embed` | `ChunkSettings` — topic published to on success |

## Embed Worker (`packages/worker-embed/`)

Long-running subscriber. Terminal pipeline step — consumes embed tasks from the embed topic, generates vector embeddings for all chunks of a document, and performs bulk UPDATE on the chunks table (no downstream publish).

### Module layout

| Module | Role |
|---|---|
| `config.py` | `EmbedSettings(BaseSettings)` — reads `EMBED_TOPIC` (default `"embed"`). `get_embed_settings()` is `@lru_cache`. |
| `service.py` | `process_embedding()` async function — orchestration using functional DI (all deps as parameters) |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, registers handler, installs signal handlers, calls `subscriber.start()` |

### `process_embedding()` (functional DI)

`process_embedding(document_id, task_id, chunk_repo, task_repo, embedding_provider, session)`:

1. Gets task; skips if already `completed`; marks `processing` and commits
2. Fetches all chunks for document via `chunk_repo.get_by_document_id(document_id)` — fails with `ValueError` if empty (chunk worker must run first)
3. Extracts embed texts: `chunk.contextual_text or chunk.chunk_text` for each chunk (embeds contextual text, falls back to raw text if None)
4. Calls `embedding_provider.embed(texts)` — single batch call for all chunks
5. Validates: vector count matches chunk count; each vector is exactly 1024 dimensions
6. Calls `chunk_repo.update_embeddings([(chunk_id, vector), ...])` — bulk UPDATE on embedding column
7. Marks task `completed`; on any exception: rolls back, marks `failed` with error message, re-raises

### `update_embeddings()` (shared repo)

`ChunkRepository.update_embeddings(updates: list[tuple[UUID, list[float]]]) -> None` executes individual async UPDATE statements setting only the `embedding` column. The `tsv` column is `GENERATED ALWAYS AS (to_tsvector('swedish', chunk_text)) STORED` — PostgreSQL computes it automatically at INSERT time and it cannot be explicitly set in UPDATE statements.

### Key design decisions

- **Terminal step:** No downstream queue publish. This is the last pipeline worker.
- **Batch embedding:** All chunks for a document in one `embed()` call — efficient for 10–50 chunks per legal document.
- **tsv is GENERATED ALWAYS:** The `chunks.tsv` column is populated by PostgreSQL at chunk INSERT time from `chunk_text`. The embed worker does not touch `tsv` — attempting to UPDATE a GENERATED ALWAYS STORED column in PostgreSQL would fail with an error.
- **Idempotency:** UPDATE semantics (overwrite embedding), no duplicate chunks created.
- **Functional DI:** Same pattern as `process_chunking()` — all dependencies as parameters, no class instance.

### Config variables

| Var | Default | Used by |
|---|---|---|
| `EMBED_TOPIC` | `embed` | `EmbedSettings` — subscribe topic |

## Worker Architecture

### Two worker patterns

- **One-shot workers** (e.g., crawl): Run once, process all items, exit. Launched by Cloud Scheduler via Cloud Run Jobs. Entry point calls `asyncio.run()`, logs the result, then exits.
- **Subscriber workers** (e.g., download, parse): Register a queue handler, block on messages. Suitable for Cloud Run triggered by Pub/Sub push. Entry point installs signal handlers and calls `subscriber.start()`.

### Service layer pattern

Workers use dependency injection with no global state. Earlier workers (crawl, download) use a service class with constructor injection. The parse worker (and subsequent workers) use a functional approach: a module-level `process_*` async function that takes all dependencies as parameters. Both patterns are equivalent — the `__main__.py` handler closure captures the shared infrastructure objects and passes them on each call.

**Worker lifecycle (subscriber workers):**

1. Receive queue message (`task_id`, `document_id`, `payload`)
2. Mark task `processing` and commit (checkpoint — durable before I/O begins)
3. Call `service.process_*()` — business logic
4. Mark task `completed`, commit, publish to next topic (commit-before-publish invariant)
5. On any exception: rollback session, mark task `failed` with `error_message`, commit; re-raise if caller needs to see it

The `process_*` function never swallows exceptions silently — either it completes cleanly or the task row reflects the failure.

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

## API Package — Service Layer (`packages/api/`)

The `api` package hosts the FastAPI application and the retrieval pipeline service layer. It depends on `shared` (repositories, DTOs, storage) and `ai` (decompose, synthesize, embedding).

### Config (`api/config.py`)

`RetrievalSettings(BaseSettings)` reads retrieval tuning parameters:

| Field | Env var | Default | Purpose |
|---|---|---|---|
| `retrieval_top_k` | `RETRIEVAL_TOP_K` | `8` | How many chunks to return from RRF fusion |
| `retrieval_search_limit` | `RETRIEVAL_SEARCH_LIMIT` | `20` | Results per arm (vector + text) before fusion |
| `retrieval_rerank_enabled` | `RETRIEVAL_RERANK_ENABLED` | `False` | Enable optional LLM rerank step (default OFF — see NFR1 <5s) |

`get_retrieval_settings()` returns a cached singleton (`@lru_cache(maxsize=1)`).

### Service Layer (`api/services/`)

Three focused modules implement the retrieval pipeline, consumed by endpoint handlers (Story 10):

#### `query_planner.py`

`QueryPlan` DTO: `semantic_query: str`, `filter: DocumentFilter`.

`plan_query(question, history, *, llm_provider=None) -> QueryPlan`:
- Calls `ai.decompose_query()` to produce a `DecomposeResult`
- Maps the result onto `DocumentFilter`:
  - `DateFilter.start/end` → `date_from/date_to`
  - `categories[0]` (first category, if any) → `category`
  - `entity_refs` → `entity_names`
- Returns `QueryPlan(semantic_query=result.semantic_query, filter=doc_filter)`

The `shared` package is not aware of `ai.dtos.DecomposeResult` — this mapping lives exclusively in the `api` service layer.

#### `retriever.py`

`RetrievedChunk` DTO: `chunk_id`, `document_id`, `chunk_text`, `chunk_index` (from chunk), plus `case_number`, `decision_date`, `decision_outcome`, `category`, `gcs_uri`, `source_url` (from document).

`retrieve(plan, session, *, embedding_provider, settings) -> list[RetrievedChunk]`:

1. **Pre-filter:** If filter is non-empty, calls `SearchRepository.find_candidate_documents(plan.filter)`. If that returns `[]`, logs a warning and falls back to `candidate_ids = None` (unfiltered). If filter is empty, skips the DB call entirely and uses `None` directly.
2. **Embed:** `embedding_provider.embed(["query: " + plan.semantic_query])` — the `"query: "` prefix is required by e5 models; chunks at index time use `"passage: "` (see worker-embed).
3. **Hybrid search:** `asyncio.gather(vector_search(...), text_search(...))` both limited to `RETRIEVAL_SEARCH_LIMIT` per arm, filtered to candidate set when non-None.
4. **RRF fusion:** `shared.search.rrf.rrf_fuse([vector_ids, text_ids])[:RETRIEVAL_TOP_K]`
5. **Optional rerank:** If `RETRIEVAL_RERANK_ENABLED`, calls `_rerank()` — a single `llm_core.generate_structured()` call that returns ranked indices; any failure falls back to RRF order (rerank never breaks retrieval).
6. **Document metadata:** `asyncio.gather(*[doc_repo.get_by_id(did) for did in unique_doc_ids])` to hydrate `RetrievedChunk` DTOs.

**e5 prefix convention:** Queries must be embedded with `"query: "` prefix; passages (at index time) use `"passage: "`. These are symmetric and must stay consistent — changing one requires changing the other and re-indexing.

#### `answerer.py`

Typed events for the SSE endpoint:

| Type | Fields | Purpose |
|---|---|---|
| `TokenEvent` | `type="token"`, `text: str` | One streaming LLM token |
| `SourcesEvent` | `type="sources"`, `sources: list[SourceReference]` | All source cards, sent after synthesis |
| `DoneEvent` | `type="done"` | Pipeline complete |

`AnswerEvent = TokenEvent | SourcesEvent | DoneEvent`

`SourceReference` DTO: `case_number`, `decision_date` (ISO string), `decision_outcome`, `category`, `excerpt` (first 200 chars of chunk), `pdf_url` (from `storage.get_url("documents/{doc_id}/original.pdf")`).

`answer_query(question, history, session, *, embedding_provider, settings, storage=None, llm_provider=None) -> AsyncIterator[AnswerEvent]`:
- Calls `plan_query()` → `retrieve()` → `ai.synthesize_answer()` (streaming)
- Yields `TokenEvent` for each LLM token
- Yields `SourcesEvent` with deduplicated sources (one card per document, first-seen chunk wins)
- Yields `DoneEvent`
- `pdf_url` is generated via `storage.get_url()` if storage is provided; `None` on error or missing storage

**Source deduplication:** Multiple chunks from the same document (`document_id`) produce exactly one `SourceReference`, ordered by fused rank (first-seen chunk in the RRF-ordered list wins the excerpt).

## Design Principles

- **Interface abstraction everywhere:** LLM provider, embedding model, storage backend (GCS/local), queue (Pub/Sub/local) — all swappable via config for local dev and future flexibility.
- **DTOs as boundaries:** Pydantic models define the contract between layers. ORM objects never cross the repo boundary.
- **Workers are thin:** Each worker's service layer does one thing. Complexity lives in `shared` and `ai`.
- **Config over code:** Model selection, provider keys, DB connection, queue config — all environment-driven.
