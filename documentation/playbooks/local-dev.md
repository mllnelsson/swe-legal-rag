---
type: Playbook
title: Local Development Environment
description: How to run the whole system locally — Postgres via Compose on Linux or Homebrew on macOS, application code on the host via uv, optionally in containers — by swapping GCP dependencies for local equivalents via environment variables.
tags: [local-dev, postgres, homebrew, docker, environment, workflow]
timestamp: 2026-08-01T00:00:00Z
---

# Local Development Environment

## Principle

Every GCP dependency has a local equivalent. Swapping between local and GCP is a config
change via environment variables — no code changes.

Postgres is the only required dependency. **How you get it is platform-dependent** — a
container on Linux, a native install on macOS — but everything above the
`DATABASE_URL` is identical either way. Application code always runs directly on the
host via `uv`.

## Postgres + pgvector

The only required dependency. Runs the same SQL interface as Cloud SQL.

- Postgres **17**, pgvector **0.8.5**, on `localhost:5432`
- Swedish text search config available out of the box (built into Postgres)
- Application code connects via `asyncpg` (async driver); Alembic migrations use the
  sync `psycopg` driver. Both are configured automatically by `shared/db.py` — the
  `DATABASE_URL` env var may use any `postgresql://` scheme.

Pick the path for your platform. Both end at the same place: a server on
`localhost:5432` owning an `overklagan` database that
`postgresql://postgres:postgres@localhost:5432/overklagan` reaches. Do not run both —
they contend for port 5432.

### Linux — Docker Compose

```bash
docker compose up -d db     # ankane/pgvector, healthchecked, persistent volume
```

The image's entrypoint applies `docker/init.sql`, which enables the extension and
creates the `overklagan_test` database the integration suite needs. The `postgres` role
and the `overklagan` database come from the image's own environment, so
`.env.example`'s `DATABASE_URL` works with no further setup.

`docker-entrypoint-initdb.d` only runs on a **first** initialisation of the `pgdata`
volume. On a volume that predates the test database, create it by hand:

```bash
docker compose exec db createdb -U postgres -O postgres overklagan_test
```

### macOS — Homebrew (native)

Docker Desktop on macOS runs Postgres inside a VM, which buys nothing here and costs
bind-mount performance. Install natively instead:

```bash
brew install postgresql@17 pgvector
brew services start postgresql@17
```

`pgvector` is a separate formula — installing `postgresql@17` alone does not provide it.
The 0.8.5 bottle builds against both `postgresql@17` and `postgresql@18`, so either
Postgres version works.

`postgresql@17` is a **keg-only** versioned formula, so Homebrew does not link its `bin`
onto `PATH` and `psql`, `createdb` and `pg_config` are not found. Add it to your shell
profile once — Intel Macs use the `/usr/local` prefix, Apple Silicon `/opt/homebrew`:

```bash
echo 'export PATH="/usr/local/opt/postgresql@17/bin:$PATH"' >> ~/.zshrc
```

Homebrew's `initdb` makes **your macOS user** the superuser, so the `postgres` role does
not exist. Creating it is what lets `DATABASE_URL` stay exactly as `.env.example` ships
it, identical to the Linux path:

```bash
createuser -s postgres
createdb -O postgres overklagan
createdb -O postgres overklagan_test   # integration tests only; see below
```

Local connections use trust authentication, so the password in
`postgresql://postgres:postgres@localhost:5432/overklagan` is never checked — only the
role has to exist. That keeps one `DATABASE_URL` working across platforms and the
optional containers.

### The test database (both platforms)

Integration tests truncate every table before each test, so they run against
`overklagan_test`, never `overklagan`. The name is derived from `DATABASE_URL` by
appending `_test`, so creating the database is the whole setup — no env var needed.
`TEST_DATABASE_URL` overrides the derived default; pointing it at the same database as
`DATABASE_URL` aborts the run rather than truncating. See
[testing](/testing.md) for the resolution rules.

The database needs no migrating by hand: the test fixtures run `alembic upgrade head`
against it on first use, which also installs the `vector` extension.

### Migrations (both platforms)

```bash
uv run alembic upgrade head
```

`alembic/versions/001_initial_schema.py` runs `CREATE EXTENSION IF NOT EXISTS vector`
itself, so the extension needs no separate step — `docker/init.sql`'s `CREATE EXTENSION`
is belt-and-braces. Its `CREATE DATABASE overklagan_test` is not: on the Compose path
that is where the test database comes from. Verify with `psql -d overklagan -c '\dx'`,
which must list `vector | 0.8.5`.

## Optional Docker Compose Services

These have no native equivalent set up and are only reachable through Docker. Both are
optional, and neither is needed for ordinary development.

### MinIO (optional)

S3-compatible object storage. Only needed if you want GCS API parity. For most
development, local filesystem storage is simpler and sufficient.

- Image: `minio/minio`
- Ports: `9000` (API), `9001` (console)
- Single bucket pre-created on startup

### Redis (optional)

Only needed if testing async queue behavior. For most development, the in-process
synchronous queue implementation is faster to work with and easier to debug.

- Image: `redis:7-alpine`
- Port: `6379`

## What Runs on the Host

Application code runs on the host, against the Homebrew Postgres. This keeps iteration
fast — no rebuilds, no container restarts.

- **API server:** `uv run` the FastAPI app directly with hot reload
- **Workers:** `uv run` each worker as a standalone process, or invoke the service layer
  directly from a script/REPL
- **Migrations:** `uv run alembic upgrade head`

This is the default, not a constraint. The same code also runs in containers behind the
`app` compose profile — see [Running in Containers](#running-in-containers).

## Environment Config

A root `.env` file provides all configuration. Each interface reads from environment
variables to select the local implementation.

```
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/overklagan
# TEST_DATABASE_URL=…/overklagan_test   # integration tests only; defaults to
                                        # DATABASE_URL's name + "_test"

# Storage — "local" uses filesystem, "gcs" uses GCS client
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./data/pdfs
GCS_BUCKET=                     # required when STORAGE_BACKEND=gcs

# Queue — "sync" for in-process, "pubsub" for GCP Pub/Sub
QUEUE_BACKEND=sync
PUBSUB_PROJECT_ID=              # required when QUEUE_BACKEND=pubsub

# AI — provider keys, model selection
# "berget" is the default LLM provider (OpenAI-compatible, https://api.berget.ai/v1).
# "gemini" remains fully supported — set LLM_PROVIDER=gemini and GEMINI_API_KEY,
# and also override the three LLM_MODEL_* vars below to valid Gemini model names.
LLM_PROVIDER=berget
BERGET_API_KEY=                # required for LLM_PROVIDER=berget and/or EMBEDDING_PROVIDER=berget
LLM_BASE_URL=                   # optional override; defaults to https://api.berget.ai/v1
GEMINI_API_KEY=                 # required only if LLM_PROVIDER=gemini

# Per-task model assignment (see /packages/ai.md — per-task model selection).
# Defaults are Berget model IDs; override all three if switching LLM_PROVIDER=gemini.
LLM_MODEL_STRUCTURED=mistralai/Mistral-Small-3.2-24B-Instruct-2506
LLM_MODEL_SUMMARIZE=mistralai/Mistral-Medium-3.5-128B
LLM_MODEL_CHAT=zai-org/GLM-5.2

# "berget" is the default embedding provider (Berget-hosted, same model as "local").
# "local" runs sentence-transformers in-process — no API key, no network access.
EMBEDDING_PROVIDER=berget
# Passed verbatim to the provider (Berget model id, or SentenceTransformer() for "local")
EMBEDDING_MODEL=intfloat/multilingual-e5-large

# Must match the model's output width (e5-large=1024, e5-base=768)
EMBEDDING_DIMENSION=1024

# LLM trace capture (see /observability.md). On by default; traces land under
# {LOCAL_STORAGE_PATH}/{LLM_TRACE_KEY_PREFIX}/{date}/*.jsonl, one object per
# flushed batch. Records carry model + tokens; cost is an analysis step.
LLM_TRACE_ENABLED=true
LLM_TRACE_KEY_PREFIX=llm-traces
LLM_TRACE_QUEUE_SIZE=1000
LLM_TRACE_FLUSH_TIMEOUT=5.0
LLM_TRACE_BATCH_SIZE=100
LLM_TRACE_BATCH_SECONDS=5.0
# Ask the provider for token usage on streamed responses. Turn off only if a
# host rejects the parameter — it fails the whole call, and streaming is chat.
LLM_STREAM_USAGE=true

# Optional services
MINIO_ENDPOINT=http://localhost:9000
REDIS_URL=redis://localhost:6379
```

## Worker Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `CRAWL_API_KEY` | *(required)* | API key for the Svenska kyrkan OData endpoint. Not defaulted in code — see [crawl source](/reference/crawl-source.md) |
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
| `RETRIEVAL_INCLUDE_APPENDICES` | `false` | Search appended lower-instance decisions too. Default OFF — see [body-first retrieval](/decisions/body-first-retrieval.md) (`api`) |
| `API_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins for the API server; Vite dev server default |
| `SESSION_MAX_HISTORY_TURNS` | `10` | Max conversation turns passed to LLM; full history stays in DB |
| `LLM_TRACE_ENABLED` | `true` | Capture every LLM/embedding call to storage — see [observability](/observability.md). Off means no recorder, no thread, no files |
| `LLM_TRACE_KEY_PREFIX` | `llm-traces` | Storage key prefix for the daily trace directories |
| `LLM_TRACE_QUEUE_SIZE` | `1000` | Records buffered before the recorder starts dropping rather than blocking an LLM call |
| `LLM_TRACE_FLUSH_TIMEOUT` | `5.0` | Seconds `flush()` and process shutdown will wait for the writer |
| `LLM_TRACE_BATCH_SIZE` | `100` | Records written per object. Batching is what keeps an object store from getting one write per call |
| `LLM_TRACE_BATCH_SECONDS` | `5.0` | How long a partial batch waits before being written; also the loss window on a hard kill |
| `LLM_STREAM_USAGE` | `true` | Ask the provider for token usage on streamed responses. Turn off only if a host rejects the parameter |

## Running the Pipeline Locally

With `QUEUE_BACKEND=sync`, publishing a message from the crawl worker dispatches it
inline to the download worker in the same process:

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
- Requires `BERGET_API_KEY` in `.env` by default — summary generation calls the
  `summarize`-role model (Mistral Medium 3.5 by default) via Berget, through the
  [ai package](/packages/ai.md). If `LLM_PROVIDER=gemini`, requires `GEMINI_API_KEY` and
  a valid Gemini model in `LLM_MODEL_SUMMARIZE` instead.

**worker-embed notes:**
- Default `EMBEDDING_PROVIDER=berget` calls Berget's hosted
  `intfloat/multilingual-e5-large` over HTTP — requires `BERGET_API_KEY`, no local model
  download, no cold start (see [embedding hosting](/decisions/embedding-hosting.md)).
- Set `EMBEDDING_PROVIDER=local` to run `sentence-transformers` in-process instead — no
  API key required, but the ~2.2 GB model is downloaded to the HuggingFace cache on first
  use, so the first embed (and the first API query, if the API is also configured for
  `local`) is slow. Subsequent runs use the cached model.

## Running in Containers

**Optional, and separate from the `db` service above.** Running *application code* in
containers is a different choice from running Postgres in one: a macOS setup with native
Postgres never needs this, and a Linux setup using `docker compose up -d db` still runs
its application code on the host by default. This path exists for CI, for a
container-parity check, and because the repo-root `Dockerfile` is the closest thing to a
Cloud Run image.

Two compose services run application code from a single image built by the repo-root
`Dockerfile` (`python:3.12-slim` + `uv sync --all-packages`). Both sit behind the `app`
profile, so plain `docker compose up -d` starts Postgres only.

| Service | Command | Shape |
|---|---|---|
| `pipeline` | `python scripts/run_pipeline.py` | One-shot: crawl → … → embed, then exits. `restart: "no"` |
| `api` | `uvicorn api.main:app --host 0.0.0.0 --port 8000` | Long-running, published on host port 8000 |

**One image, two services — and one pipeline container, not seven.** A container per
worker cannot work while `QUEUE_BACKEND=sync`: the broker is a module-level singleton and
a publish is a direct call into a handler registered in the *same* process, so each
worker container would hold an empty broker and fail on its first publish. Seven
containers matching the Cloud Run topology need a real queue backend first — that is
[story 12 / GCP layout](/reference/gcp-layout.md) territory.

```bash
docker compose build
docker compose up -d db                                  # healthcheck gates the rest
docker compose run --rm pipeline alembic upgrade head    # dev group carries alembic

docker compose run --rm pipeline                                          # current year
docker compose run --rm pipeline python scripts/run_pipeline.py --years all

docker compose --profile app up -d api                   # http://localhost:8000
docker compose --profile app down
```

### Environment the containers override

`.env` is loaded via `env_file`, then these two are overridden in `docker-compose.yml`
because the host values are wrong inside a container:

| Variable | Host value | Container value | Why |
|---|---|---|---|
| `DATABASE_URL` | `…@localhost:5432/…` | `…@db:5432/…` | `localhost` in a container is the container |
| `LOCAL_STORAGE_PATH` | `./data/pdfs` | `/data/pdfs` | Relative to CWD otherwise; must be absolute and match the mount |

`./data:/data` is a single bind mount carrying both the PDF tree and the trace stream.
`LOCAL_STORAGE_PATH` is set to the same `pdfs` subdirectory the host uses, so storage
keys resolve to the same files either way — a PDF downloaded on the host is readable by
a container run, and traces from host, `pipeline` and `api` all land under
`data/pdfs/llm-traces/{date}/`.

Traces need nothing special from the mount. `./data` is a *directory* bind mount, and the
recorder writes one **new** `.jsonl` object per flushed batch rather than appending to a
shared file — so new objects appear on the host as they are written, a batch that
straddles UTC midnight splits into the right day, and host, `pipeline` and `api` never
contend over the same file. See [observability](/observability.md) for the layout.

The image is for local development only. It installs the dev dependency group (that is
where `alembic` comes from) and the whole workspace; a Cloud Run image wants neither.

## Interface Mapping

| Concern | Env var | Local value | GCP value |
|---|---|---|---|
| Database | `DATABASE_URL` | `postgresql://...@localhost:5432/...` | Cloud SQL connection string |
| Test database | `TEST_DATABASE_URL` | *(derived: `DATABASE_URL` + `_test`)* | Set explicitly in CI |
| Storage | `STORAGE_BACKEND` | `local` (filesystem) | `gcs` |
| Storage bucket | `GCS_BUCKET` | *(not needed)* | GCS bucket name |
| Queue | `QUEUE_BACKEND` | `sync` (in-process) | `pubsub` |
| Queue project | `PUBSUB_PROJECT_ID` | *(not needed)* | GCP project ID |
| Secrets | — | `.env` file | Secret Manager |
| Embedding dim | `EMBEDDING_DIMENSION` | `1024` | `1024` — must match `EMBEDDING_MODEL` in both environments |
| LLM provider | `LLM_PROVIDER` | `berget` (default) or `gemini` | Same — no local/GCP distinction, just a config choice |
| Embedding provider | `EMBEDDING_PROVIDER` | `berget` (default) or `local` | Same — `local` is an offline dev/test fallback, not a GCP-vs-local split |

Development defaults: `STORAGE_BACKEND=local` and `QUEUE_BACKEND=sync`. No GCS or Pub/Sub
credentials required for local development. The full local↔GCP mapping and the
abstraction principle behind it are described in the
[GCP layout](/reference/gcp-layout.md).

## Local Queue Behavior

The `sync` queue backend calls the next worker's service layer directly in-process. This
means the full pipeline can run as a single Python invocation — useful for debugging and
testing the complete ingestion flow without any infrastructure.

For testing async/concurrent behavior, switch to `redis` and run workers as separate
processes.

## First-time Setup

```bash
# 1. Postgres — see "Postgres + pgvector" above; one of:
docker compose up -d db                              # Linux
brew install postgresql@17 pgvector && \
  brew services start postgresql@17 && \
  createuser -s postgres && \
  createdb -O postgres overklagan && \
  createdb -O postgres overklagan_test                        # macOS

# 2. The rest is identical on both
cp .env.example .env        # copy config template — DATABASE_URL needs no edit
uv sync --all-packages      # install all workspace packages
uv run alembic upgrade head # apply migrations; also creates the vector extension

# 3. Check it works. Unit tests need none of the above; integration tests need all of it.
uv run pytest               # unit only, by design
uv run pytest -m integration
```

Verify before going further — `psql -d overklagan -c '\dx'` lists `vector | 0.8.5`, and
`psql -d overklagan -c '\d chunks'` shows `embedding | vector(1024)` with the
`ix_chunks_embedding_hnsw` and `ix_chunks_tsv_gin` indexes.

## Typical Dev Workflow

Postgres runs in the background either way — a Compose service or a `brew services`
daemon — so there is nothing to start each day.

1. `uv run alembic upgrade head` — apply any new migrations
2. Start the API: `uv run --package api uvicorn api.main:app --reload`
3. Run the pipeline: `uv run python scripts/run_pipeline.py`
4. Iterate — code changes reflect immediately, no container rebuilds

## Data Seeding

For development, keep a small set of test PDFs in a `data/seed/` directory (gitignored).
A seed script runs the full pipeline synchronously against these documents to populate
the local database with realistic data for frontend and retrieval development.

## Approved Docker Images

Applies wherever containers are used — the Linux `db` service, the optional
[container path](#running-in-containers). A macOS native setup uses none of them. Only
the images listed below are approved for use in this project. Pin to the tags shown — do
not use `latest` or switch to alternative images without discussion.

| Service | Image | Tag | Purpose |
|---|---|---|---|
| Postgres + pgvector | `ankane/pgvector` | (default / latest stable) | SQL database with vector search |
| MinIO | `minio/minio` | (default / latest stable) | S3-compatible object storage |
| Redis | `redis` | `7-alpine` | Async queue / cache |
| Python | `python` | `3.12-slim` | Application base image |

When adding a new infrastructure service, add its image here before using it in
`docker-compose.yml`.

**Berget.ai (LLM + embedding provider) needs no entry here.** It's an external HTTP API
called from existing application processes (`api`, workers) — not a service this project
runs, so it never touches `docker-compose.yml` or this table.

## Docker Compose Profiles

Use Compose profiles to keep the default startup minimal:

- **Default (no profile):** Postgres only — the minimum viable dev environment
- **`full`:** Postgres + MinIO + Redis — for testing with all services
