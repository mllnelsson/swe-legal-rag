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

# Queue — "sync" for in-process, "redis" for Redis Streams, "pubsub" for GCP
QUEUE_BACKEND=sync

# AI — provider keys, model selection
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=e5-multilingual

# Optional services
MINIO_ENDPOINT=http://localhost:9000
REDIS_URL=redis://localhost:6379
```

## Interface Mapping

| Concern | Env var | Local value | GCP value |
|---|---|---|---|
| Database | `DATABASE_URL` | `postgresql://...@localhost:5432/...` | Cloud SQL connection string |
| Storage | `STORAGE_BACKEND` | `local` | `gcs` |
| Queue | `QUEUE_BACKEND` | `sync` | `pubsub` |
| Secrets | — | `.env` file | Secret Manager |

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

## Docker Compose Profiles

Use Compose profiles to keep the default startup minimal:

- **Default (no profile):** Postgres only — the minimum viable dev environment
- **`full`:** Postgres + MinIO + Redis — for testing with all services
