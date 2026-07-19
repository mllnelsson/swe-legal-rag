# Local Development Environment

## Principle

Every GCP dependency has a local equivalent. Swapping between local and GCP is a config change via environment variables — no code changes. Docker Compose manages the infrastructure services; application code runs directly on the host via `uv`.

## Docker Compose Services

### Postgres + pgvector

The only required service. Runs the same SQL interface as Cloud SQL.

- Image: `ankane/pgvector`
- Port: `5432`
- Persistent volume for data across restarts
- Initialized with pgvector extension enabled
- Swedish text search config available out of the box (built into Postgres)
- Application code connects via `asyncpg` (async driver); Alembic migrations use the sync `psycopg` driver. Both are configured automatically by `shared/db.py` — the `DATABASE_URL` env var may use any `postgresql://` scheme.

### MinIO (optional)

S3-compatible object storage. Only needed if you want GCS API parity. For most development, local filesystem storage is simpler and sufficient.

- Image: `minio/minio`
- Ports: `9000` (API), `9001` (console)
- Single bucket pre-created on startup

### Redis (optional)

Only needed if testing async queue behavior. For most development, the in-process synchronous queue implementation is faster to work with and easier to debug.

- Image: `redis:7-alpine`
- Port: `6379`

## What Runs Outside Compose

Application code runs on the host, not in containers. This keeps iteration fast — no rebuilds, no container restarts.

- **API server:** `uv run` the FastAPI app directly with hot reload
- **Workers:** `uv run` each worker as a standalone process, or invoke the service layer directly from a script/REPL
- **Migrations:** `uv run alembic upgrade head` against the Docker Postgres instance

## Environment Config

A root `.env` file provides all configuration. Each interface reads from environment variables to select the local implementation.

```
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/overklagan

# Storage — "local" uses filesystem, "gcs" uses GCS client
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./data/pdfs
GCS_BUCKET=                     # required when STORAGE_BACKEND=gcs

# Queue — "sync" for in-process, "pubsub" for GCP Pub/Sub
QUEUE_BACKEND=sync
PUBSUB_PROJECT_ID=              # required when QUEUE_BACKEND=pubsub

# AI — provider keys, model selection
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=e5-multilingual

# Embedding dimension (768=e5-multilingual, 1024=Cohere)
EMBEDDING_DIMENSION=768

# Optional services
MINIO_ENDPOINT=http://localhost:9000
REDIS_URL=redis://localhost:6379
```

## Worker Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `CRAWL_API_KEY` | *(required)* | API key for the Svenska kyrkan OData endpoint. Not defaulted in code — see [CRAWL_SOURCE.md](CRAWL_SOURCE.md) |
| `CRAWL_YEARS` | `current` | Decision years to crawl: `current`, `all`, `2019`, `2019-2021`, or a comma-separated mix. `--years` overrides it |
| `CRAWL_API_BASE` | `https://www.svenskakyrkan.se/webapi/api-v3/odata/` | OData v4 service root |
| `CRAWL_DOCUMENT_URL_TEMPLATE` | `https://www.svenskakyrkan.se/default.aspx?id={document_id}&ptid=` | Template for the canonical PDF URL stored as `documents.source_url` |
| `CRAWL_WEB_ID` | `1374643` | Svenska kyrkan web whose documents are listed |
| `CRAWL_PAGE_SIZE` | `100` | Rows per `$top`/`$skip` page |
| `CRAWL_RATE_LIMIT_DELAY` | `0.5` | Seconds to sleep between listing pages |
| `CRAWL_MAX_RETRIES` | `3` | Retry attempts for 5xx / connect / timeout errors |
| `CRAWL_REQUEST_TIMEOUT` | `30` | HTTP timeout (seconds) for listing requests |
| `CRAWL_TOPIC` | `download` | Queue topic crawl publishes to |
| `DOWNLOAD_REQUEST_TIMEOUT` | `60` | HTTP timeout (seconds) for PDF downloads |
| `DOWNLOAD_MAX_RETRIES` | `3` | Max retry attempts for transient errors |
| `DOWNLOAD_RATE_LIMIT_DELAY` | `0.5` | Seconds to sleep after each successful download |
| `EXTRACT_STRATEGY` | `rule_based_with_llm_fallback` | Extraction strategy for worker-extract: `rule_based` (regex only, no LLM cost), `llm` (LLM only — requires a configured LLM provider), `rule_based_with_llm_fallback` (regex first, LLM when result is sparse) |
| `CHUNK_TOPIC` | `chunk` | Queue topic worker-chunk subscribes to |
| `CHUNK_NEXT_TOPIC` | `embed` | Queue topic worker-chunk publishes to |
| `EMBED_TOPIC` | `embed` | Queue topic worker-embed subscribes to |
| `RETRIEVAL_TOP_K` | `8` | How many chunks to return after RRF fusion (`api`) |
| `RETRIEVAL_SEARCH_LIMIT` | `20` | Results per arm (vector + text) before fusion (`api`) |
| `RETRIEVAL_RERANK_ENABLED` | `false` | Enable optional LLM rerank step — default OFF for NFR1 <5s (`api`) |
| `API_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins for the API server; Vite dev server default |
| `SESSION_MAX_HISTORY_TURNS` | `10` | Max conversation turns passed to LLM; full history stays in DB |

## Running the Pipeline Locally

With `QUEUE_BACKEND=sync`, publishing a message from the crawl worker dispatches it inline to the download worker in the same process:

```bash
# Full pipeline in one invocation (sync queue):
uv run --package worker-crawl python -m worker_crawl

# Or run each worker independently (useful with pubsub or for debugging):
uv run --package worker-crawl python -m worker_crawl
uv run --package worker-download python -m worker_download
uv run --package worker-parse python -m worker_parse
uv run --package worker-metadata python -m worker_metadata
uv run --package worker-extract python -m worker_extract
uv run --package worker-chunk python -m worker_chunk
uv run --package worker-embed python -m worker_embed
```

**worker-chunk notes:**
- Requires `GEMINI_API_KEY` in `.env` — summary generation calls Gemini Flash via the `ai` package.

**worker-embed notes:**
- Default `EMBEDDING_PROVIDER=local` with `EMBEDDING_MODEL=e5-multilingual` runs embedding via `sentence-transformers` locally — no API key required.
- First run downloads `intfloat/multilingual-e5-base` (~1.1 GB one-time to the HuggingFace cache). Subsequent runs use the cached model.

## Interface Mapping

| Concern | Env var | Local value | GCP value |
|---|---|---|---|
| Database | `DATABASE_URL` | `postgresql://...@localhost:5432/...` | Cloud SQL connection string |
| Storage | `STORAGE_BACKEND` | `local` (filesystem) | `gcs` |
| Storage bucket | `GCS_BUCKET` | *(not needed)* | GCS bucket name |
| Queue | `QUEUE_BACKEND` | `sync` (in-process) | `pubsub` |
| Queue project | `PUBSUB_PROJECT_ID` | *(not needed)* | GCP project ID |
| Secrets | — | `.env` file | Secret Manager |
| Embedding dim | `EMBEDDING_DIMENSION` | `768` | model-dependent |

Development defaults: `STORAGE_BACKEND=local` and `QUEUE_BACKEND=sync`. No GCS or Pub/Sub credentials required for local development.

## Local Queue Behavior

The `sync` queue backend calls the next worker's service layer directly in-process. This means the full pipeline can run as a single Python invocation — useful for debugging and testing the complete ingestion flow without any infrastructure.

For testing async/concurrent behavior, switch to `redis` and run workers as separate processes.

## First-time Setup

```bash
cp .env.example .env        # copy config template
uv sync --all-packages      # install all workspace packages
docker compose up -d        # start Postgres
uv run alembic upgrade head # apply migrations
```

## Typical Dev Workflow

1. `docker compose up -d` — starts Postgres (and optionally MinIO/Redis)
2. `uv run alembic upgrade head` — apply migrations
3. Start the API: `uv run --package api uvicorn api.main:app --reload`
4. Run a worker: `uv run --package worker-crawl python -m worker_crawl`
5. Iterate — code changes reflect immediately, no container rebuilds

## Data Seeding

For development, keep a small set of test PDFs in a `data/seed/` directory (gitignored). A seed script runs the full pipeline synchronously against these documents to populate the local database with realistic data for frontend and retrieval development.

## Approved Docker Images

Only the images listed below are approved for use in this project. Pin to the tags shown — do not use `latest` or switch to alternative images without discussion.

| Service | Image | Tag | Purpose |
|---|---|---|---|
| Postgres + pgvector | `ankane/pgvector` | (default / latest stable) | SQL database with vector search |
| MinIO | `minio/minio` | (default / latest stable) | S3-compatible object storage |
| Redis | `redis` | `7-alpine` | Async queue / cache |
| Python | `python` | `3.12-slim` | Application base image |

When adding a new infrastructure service, add its image here before using it in `docker-compose.yml`.

## Docker Compose Profiles

Use Compose profiles to keep the default startup minimal:

- **Default (no profile):** Postgres only — the minimum viable dev environment
- **`full`:** Postgres + MinIO + Redis — for testing with all services
