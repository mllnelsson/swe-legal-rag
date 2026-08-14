---
type: Playbook
title: Local Development Environment
description: How to run the whole system locally — Postgres via Compose on Linux or Homebrew on macOS, application code on the host via uv, optionally in containers — by swapping GCP dependencies for local equivalents via environment variables.
tags: [local-dev, postgres, homebrew, docker, environment, workflow]
timestamp: 2026-08-09T12:00:00Z
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

### The coding agent's sandbox (both platforms)

`overklagan` holds locally crawled data that re-running the pipeline does not
reproduce, so a coding agent never writes to it. It gets a file-level copy instead,
and two mechanisms keep it there:

| Piece | What it does |
|---|---|
| `.claude/hooks/db-sandbox.sh` | `ensure` (SessionStart) copies `overklagan` to `overklagan_coding_agent` with `createdb -T` when it is missing; `refresh --yes` drops and re-copies — see [refreshing the sandbox](#refreshing-the-sandbox) |
| `.claude/settings.json` `env` | Points `DATABASE_URL` and `PGDATABASE` at the sandbox and pins `TEST_DATABASE_URL` to `overklagan_test` |
| `.claude/hooks/db-guard.sh` | A `PreToolUse` hook that refuses any Bash command that would write to a database that is not the sandbox or a `_test` one |
| `.claude/hooks/db-guard-selftest.sh` | Asserts the guard's verdict on ~37 commands, including every form in which a connection target can be declared |

The guard resolves the target before judging the statement, because `psql` takes its
database from `-d`, a bare positional, a `postgresql://` URI, a keyword/value
conninfo, `PGDATABASE`, `PGSERVICE`, or a fallback to `$USER` — most of which never
name it on the command line. Anything it cannot resolve counts as protected. Reads
against `overklagan` are allowed; writes are not.

`TEST_DATABASE_URL` has to be pinned rather than derived: the suffix rule above would
otherwise turn the redirected `DATABASE_URL` into `overklagan_coding_agent_test`,
which does not exist.

The `env` block wins over `.env` because every entrypoint calls `load_dotenv()`
without `override=True`, so a variable already in the process environment survives.
One cluster serves every worktree, so all of them share one sandbox.

#### Refreshing the sandbox

```bash
.claude/hooks/db-sandbox.sh refresh --yes
```

**`--yes` is required, and the confirmation is the user's to give — not an agent's.**
Because one cluster serves every worktree, there is exactly one sandbox, shared by
every session and every agent running against this checkout. `refresh` drops it, so
it discards their work along with yours, and nothing in the script can tell whose
was whose. Without `--yes` it refuses and exits 64, having touched nothing.

`ensure` is the opposite and needs no confirmation: it creates the sandbox only when
it is **missing** and never drops an existing one, which is why `SessionStart` can
run it and any number of sessions can start concurrently without fighting over it.

A consequence worth knowing: **a stale sandbox is the normal state**, not a fault.
`ensure` leaves it alone, so a sandbox created before a schema change or a pipeline
run keeps the data it had — it can be several migrations and a whole corpus behind
`overklagan`. Check before trusting it:

```bash
psql -d overklagan_coding_agent -tAc "select count(*) from chunks"
psql -d overklagan            -tAc "select count(*) from chunks"
```

If the two disagree and you only need to *read* real data, read `overklagan`
directly — the guard permits it, and it costs nobody their sandbox. Refresh only
when you actually need to write against current data.

`refresh` fails safely when another session is connected to the sandbox or to
`overklagan`: `dropdb` and `createdb -T` both refuse, and the script reports it and
exits 0 rather than half-copying. Close the other session and run it again.

### Migrations (both platforms)

```bash
uv run alembic upgrade head
```

`alembic/versions/001_initial_schema.py` runs `CREATE EXTENSION IF NOT EXISTS vector`
itself, so the extension needs no separate step — `docker/init.sql`'s `CREATE EXTENSION`
is belt-and-braces. Its `CREATE DATABASE overklagan_test` is not: on the Compose path
that is where the test database comes from. Verify with `psql -d overklagan -c '\dx'`,
which must list `vector | 0.8.5`.

**Run `uv run python scripts/check_semantic_model.py` after any migration that touches a
table the [SQL agent](/packages/agents.md) exposes.** It validates
[`semantic_model.yaml`](/reference/semantic-model.md) against the ORM the migration just
changed — a column added without a description, or a description left behind by a
dropped column, is the same failure `api/main.py`'s startup check would hit, found here
in a second instead of at deploy.

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

# Storage — "local" uses filesystem, "gcs" uses GCS client. The path is the
# storage root every stored key hangs off (PDFs under documents/, LLM traces
# under llm-traces/), not a PDF-specific directory — and ./data is what
# .gitignore covers.
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./data
GCS_BUCKET=                     # required when STORAGE_BACKEND=gcs

# Queue — "sync" for in-process, "pubsub" for GCP Pub/Sub
QUEUE_BACKEND=sync
PUBSUB_PROJECT_ID=              # required when QUEUE_BACKEND=pubsub

# AI — secrets only. Which model and provider each task uses lives in
# llm_config.yaml at the repo root; see /reference/llm-config.md for the file
# format, the precedence rules, and the full list of variables that override it.
BERGET_API_KEY=                 # required unless every provider is gemini/local
GEMINI_API_KEY=                 # required if any role uses provider: gemini

# Must match embedding.dimension in llm_config.yaml and the chunks.embedding
# column width (e5-large=1024, e5-base=768). Checked at startup.
EMBEDDING_DIMENSION=1024

# LLM trace capture (see /observability.md). On by default; one file per billed
# call, under {LOCAL_STORAGE_PATH}/{LLM_TRACE_KEY_PREFIX}/{date}/{interaction_id}/,
# so one directory holds everything a request cost. Records carry model + tokens;
# cost is an analysis step.
LLM_TRACE_ENABLED=true
LLM_TRACE_KEY_PREFIX=llm-traces
# Ask the provider for token usage on streamed responses. Turn off only if a
# host rejects the parameter — it fails the whole call, and streaming is chat.
LLM_STREAM_USAGE=true

# Optional services
MINIO_ENDPOINT=http://localhost:9000
REDIS_URL=redis://localhost:6379
```

An `.env` still setting `LOCAL_STORAGE_PATH=./data/pdfs` (the old default) keeps working
unchanged, since the env var always wins over the code default; anyone dropping that line
to pick up the new `./data` default just needs
`mv data/pdfs/* data/ && rmdir data/pdfs` to bring already-downloaded PDFs and traces up
one level to match.

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
| `CHAT_AGENT_MAX_ITERATIONS` | `8` | Tool-loop budget for the [conversational agent](/retrieval/chat-agent.md); the first lever when a turn misses NFR1b (`agents`) |
| `CHAT_AGENT_MAX_DOCUMENTS_READ` | `5` | Decisions the agent may read in full per run; exceeding it is a refusal, not an error (`agents`) |
| `CHAT_AGENT_MAX_CHUNKS_CITED` | `12` | Passages the answer may be built from (`agents`) |
| `CHAT_AGENT_SEARCH_LIMIT` | `8` | Decisions one agent search returns (`agents`) |
| `CHAT_AGENT_CHUNKS_PER_DECISION` | `2` | Passages per decision one agent search returns — with the setting above, what bounds how much verbatim text a tool result puts in the loop's context (`agents`) |
| `SEARCH_ARM_LIMIT` | `50` | Results per arm (vector + text) before fusion (`api`) |
| `SEARCH_MIN_VECTOR_SIMILARITY` | `0.78` | Cosine similarity a chunk must reach before `/api/search`'s vector arm returns it — what decides "no match". Model- and corpus-specific; re-measure when the [embedding model](/decisions/embedding-model.md) changes. `0` disables the floor. See [the similarity floor](/retrieval/deterministic-search.md#the-similarity-floor) (`api`) |
| `API_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins for the API server; Vite dev server default |
| `SESSION_MAX_HISTORY_TURNS` | `10` | Max conversation turns passed to LLM; full history stays in DB |
| `LLM_TRACE_ENABLED` | `true` | Capture every LLM/embedding call to a file — see [observability](/observability.md). Off means no recorder and no files |
| `LLM_TRACE_KEY_PREFIX` | `llm-traces` | Directory under `LOCAL_STORAGE_PATH` holding the daily trace tree |
| `LLM_STREAM_USAGE` | `true` | Ask the provider for token usage on streamed responses. Turn off only if a host rejects the parameter |

## Running the Pipeline Locally

With `QUEUE_BACKEND=sync`, publishing appends to a process-wide queue that only
handlers subscribed in the *same* process can serve, so a full run has to subscribe the
downstream workers before crawl publishes anything and then pump what crawl queued.
`scripts/run_pipeline.py` does exactly that; bare `python -m worker_crawl` subscribes
nothing and fails on its first publish with `QueueHandlerError: No handler registered
for topic: 'download'`. The runner also re-drives tasks left `pending` by an earlier
run — see [live testing](/playbooks/live-testing.md).

```bash
# Full pipeline in one invocation (sync queue):
uv run python scripts/run_pipeline.py

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
  [ai package](/packages/ai.md). If the `summarize` role is pointed at
  `provider: gemini`, requires `GEMINI_API_KEY` and a valid Gemini model on that role
  instead.
- **Needs the embedding model's tokenizer files at startup**, which it did not before.
  `subscribe()` builds an `ai.EmbeddingRuler` (`ai.create_embedding_ruler()`) to derive
  its chunk token budget — see [embedding window](/decisions/embedding-window.md) — and
  `AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")` contacts the
  HuggingFace hub unless the tokenizer files are already in the local HF cache. A machine
  with no hub access and no warm cache fails to start. Run the worker once with hub
  access to populate `~/.cache/huggingface`, or pre-warm it directly:
  `uv run --package worker-chunk python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('intfloat/multilingual-e5-large')"`.
  The [container path](#running-in-containers) below has the same requirement and no
  built-in cache — see its note.
- **Or opt out entirely**: `EMBEDDING_WINDOW_OVERRIDE=512` starts the worker with no
  tokenizer at all, taking the window on trust and estimating chunk sizes from character
  counts. Verified to start with an empty `HF_HOME` and `HF_HUB_OFFLINE=1`, where the
  default path fails with `LocalEntryNotFoundError`. The number must match the model —
  512 is correct for e5-large — and chunks come out roughly half size, so this is the
  fallback for a machine that cannot reach the tokenizer, not a default. See
  [embedding window](/decisions/embedding-window.md).

**worker-embed notes:**
- The checked-in `llm_config.yaml` ships `embedding.provider: local`, which runs
  `sentence-transformers` in-process — no API key required, but the ~2.2 GB model is
  downloaded to the HuggingFace cache on first use, so the first embed (and the first
  API query) is slow. Subsequent runs use the cached model.
- Point `embedding.provider` at a `providers:` entry — `berget` — to call Berget's
  hosted `intfloat/multilingual-e5-large` over HTTP instead: requires `BERGET_API_KEY`,
  no local model download, no cold start. That is the intended hosted path; see
  [embedding hosting](/decisions/embedding-hosting.md).
- The `EMBEDDING_PROVIDER` env var overrides the file, but takes an `EmbeddingBackend`
  **kind** — `openai_compatible` or `local` — not a `providers:` name, so
  `EMBEDDING_PROVIDER=berget` is not a valid value. See the
  [env-var registry](/reference/llm-config.md#env-var-registry).

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
worker cannot work while `QUEUE_BACKEND=sync`: the broker is a module-level singleton
whose queue only handlers subscribed in the *same* process can serve, so each worker
container would hold an empty broker and fail on its first publish. Seven
containers matching the Cloud Run topology need a real queue backend first — that is
[story 12 / GCP layout](/reference/gcp-layout.md) territory.

**No HuggingFace cache is baked into the image or mounted by Compose.** The `pipeline`
container's chunk step now needs the e5 tokenizer files at startup (see the worker-chunk
note above), and neither the Dockerfile nor `./data:/data` provides them — `./data` is
the PDF/trace mount, not the HF cache. Until this is added, either build the tokenizer
into the image with a `RUN` layer after `uv sync` (`python -c "from transformers import
AutoTokenizer; AutoTokenizer.from_pretrained('intfloat/multilingual-e5-large')"`) or mount
an `HF_HOME` volume pointing at a warm host cache. Without one, `docker compose run --rm
pipeline` fails at the chunk step's startup check the first time it runs with no network
egress to the hub.

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
| `LOCAL_STORAGE_PATH` | `./data` | `/data` | Relative to CWD otherwise; must be absolute and match the mount |

`./data:/data` is a single bind mount carrying both the PDF tree and the trace stream.
`LOCAL_STORAGE_PATH` is set to the mount itself, so storage keys resolve to the same
files either way — a PDF downloaded on the host is readable by a container run, and
traces from host, `pipeline` and `api` all land under `data/llm-traces/{date}/`.

Traces need nothing special from the mount. `./data` is a *directory* bind mount, and the
recorder writes one **new** `.json` file per call rather than appending to a shared one —
so files appear on the host as they are written, each lands in the day and the
interaction directory it belongs to, and host, `pipeline` and `api` never contend over
the same file. See [observability](/observability.md) for the layout.

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
| Embedding dim | `EMBEDDING_DIMENSION` | `1024` | `1024` — must match `embedding.model` in both environments |
| LLM provider | `llm_config.yaml` `roles.*.provider` | `berget` (default) or `gemini`, per role | Same — no local/GCP distinction, just a config choice |
| Embedding provider | `llm_config.yaml` `embedding.provider` | `local` (default, as shipped) or `berget` | Same — no GCP-vs-local split; `berget` is the intended hosted path once a key is configured, `local` the offline fallback |

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
