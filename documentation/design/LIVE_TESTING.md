# Live Testing Guide

How to run the system locally end-to-end for manual testing and verification.

## Prerequisites

1. Docker running (`docker compose up -d` — starts Postgres with pgvector)
2. Dependencies installed: `uv sync --all-packages`
3. Environment configured: `cp .env.example .env` and edit values (see below)
4. Migrations applied: `uv run alembic upgrade head`

## Required Environment Variables

Edit `.env` before running. Minimum required for a full pipeline run:

```bash
# Must set — no default. Client-side key used by the public decision search on
# svenskakyrkan.se; read it from the site's own network requests.
# See documentation/design/CRAWL_SOURCE.md
CRAWL_API_KEY=<api-key>

# Which decision years to crawl: current (default) | all | 2019 | 2019-2021
CRAWL_YEARS=current

# Must set — needed by metadata worker LLM fallback
GEMINI_API_KEY=<your-key>

# Defaults are fine for local dev
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/overklagan
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./data/pdfs
QUEUE_BACKEND=sync
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=intfloat/multilingual-e5-large
EMBEDDING_DIMENSION=1024
```

## Pipeline Overview

The ingestion pipeline flows through workers connected by queue topics:

```
crawl → [topic: download] → download → [topic: parse] → parse → [topic: metadata] → metadata → [topic: extract] → extract → chunk → embed
```

With `QUEUE_BACKEND=sync`, each worker dispatches to the next inline — you can run the full implemented pipeline in sequence.

## Running Workers

### Option A: Full pipeline (sync queue)

With `QUEUE_BACKEND=sync`, the crawl worker triggers download inline, which triggers parse, which triggers metadata. Run from the project root:

```bash
# Current year (default)
uv run --package worker-crawl python -m worker_crawl

# Backfill the full history (~1073 documents across 2000-2026 plus the year-less tag)
uv run --package worker-crawl python -m worker_crawl --years all

# A specific year or range
uv run --package worker-crawl python -m worker_crawl --years 2019-2021
```

This will:
1. Query the OData API for the current year's decisions
2. Download new PDFs to `./data/pdfs/`
3. Parse each PDF to extract raw text
4. Extract metadata (rule-based, with LLM fallback)

### Option B: Individual workers (for debugging)

Run each worker as a separate process. Useful when `QUEUE_BACKEND` is not `sync` or to isolate a single step:

```bash
# Crawl — discovers decisions via the OData API, publishes to 'download' topic
uv run --package worker-crawl python -m worker_crawl [--years all]

# Download — listens on 'download', saves PDFs, publishes to 'parse'
uv run --package worker-download python -m worker_download

# Parse — listens on 'parse', extracts text, publishes to 'metadata'
uv run --package worker-parse python -m worker_parse

# Metadata — listens on 'metadata', extracts structured fields, publishes to 'extract'
uv run --package worker-metadata python -m worker_metadata
```

### Not yet implemented

The following workers exist as stubs only:

- `worker-extract` — entity & reference extraction (Story #7)
- `worker-chunk` — contextual chunking (Story #8)
- `worker-embed` — embedding generation (Story #8)

### Option C: Per-step runner (`scripts/run_step.py`)

For hand-testing one stage at a time — iterate on a step over a single document,
inspect what it produced, tweak the code, re-run — use the per-step runner. It
calls each worker's service function directly with a no-op queue publisher, so a
step runs and then **stops** instead of cascading to the next (which is what the
`sync` queue does in a single process). Re-running a step is safe: the current
step's task is reset to `pending` and the immediate downstream task row is
cleared first (avoids the `uq_tasks_document_id_step` unique violation).

```bash
# Discover documents, then list them with their per-step task status
uv run python scripts/run_step.py crawl            # add --years all to backfill
uv run python scripts/run_step.py docs

# Run a single step for one document (UUID from `docs`)
uv run python scripts/run_step.py download <doc_id>
uv run python scripts/run_step.py parse    <doc_id>   # re-run freely while editing the parser
uv run python scripts/run_step.py metadata <doc_id>

# Run the whole chain over one document once each step is right
uv run python scripts/run_step.py chain <doc_id>               # download..embed
uv run python scripts/run_step.py chain <doc_id> --until chunk # stop after a given step
```

#### How steps hand off (and starting mid-pipeline)

Steps do **not** pass a single JSON to each other. They communicate through the
**shared store**, which accumulates: `parse` writes `documents.json[].raw_text`,
`metadata` fills the structured fields on the same row, `extract` writes
`entities.json` / `references.json`, `chunk` writes `chunks.json`, and so on. So
"the JSON from the previous step" is just the store on disk after that step ran.

That means you can start at any step as long as the store already holds its
inputs (e.g. `extract` needs a document with `raw_text`; `case_number` is
optional). Two ways to get there:

- Run the earlier steps once, then iterate the step you care about, or
- **`seed`** a document straight from a JSON file and start there:

```bash
cat > case.json <<'JSON'
{ "source_url": "manual://test", "case_number": "2024-0099",
  "raw_text": "Beslut av Domkapitlet ... se även mål 2023-0042." }
JSON

DOC=$(uv run python scripts/run_step.py --store fs seed case.json)   # prints the new UUID
EXTRACT_STRATEGY=rule_based \
  uv run python scripts/run_step.py --store fs extract "$DOC"        # starts at extract, offline
```

`seed` accepts `source_url` plus any updatable document field (`raw_text`,
`case_number`, `decision_date`, `summary`, `decision_outcome`, `category`,
`gcs_uri`); unknown keys are ignored with a warning. Keep a library of input
fixtures by pointing `--store-dir` at different folders.

#### DB-free playground (`--store fs`)

Add `--store fs` to **any** of the commands above to run against JSON files under
`./data/store/` (override with `--store-dir`) instead of Postgres — no database,
no migrations, nothing dumped into the DB. The real worker services run unchanged;
only the injected **repo namespaces** are swapped — the real
`shared.repositories.*` modules are replaced by the file-backed doubles in
`scripts/_fsrepos/*` (backed by `scripts/_fsstore.py`). Both satisfy the same
`shared.repositories._protocols` interfaces, so no worker code changes between DB
and fs modes. Each table is a JSON file of the pydantic DTOs
(`documents.json`, `tasks.json`, `chunks.json`, `entities.json`,
`document_entities.json`, `references.json`, `unresolved.json`); PDFs still land
under `LOCAL_STORAGE_PATH` via the local storage backend. `commit()` writes the
JSON, `rollback()` reloads it, so transaction/rollback behaviour matches the DB.

```bash
uv run python scripts/run_step.py --store fs crawl
uv run python scripts/run_step.py --store fs parse <doc_id>
cat ./data/store/documents.json    # inspect the raw_text the parser produced
```

Per-step external dependencies (same in both stores): `crawl`/`download` need
network; `metadata` and `chunk` call Gemini (`GEMINI_API_KEY`); `embed` loads the
local e5 model (no API, no DB). `--store fs` synthesizes a throwaway
`DATABASE_URL` when none is set, so it works with no `.env` database config.

## Running the API Server

```bash
uv run --package api uvicorn api.main:app --reload --port 8000
```

Currently only exposes `GET /health`. Chat endpoint is Story #10.

## Verifying the Pipeline

### 1. Check Postgres for ingested data

```bash
# Connect to the database
psql postgresql://postgres:postgres@localhost:5432/overklagan

# Count documents
SELECT count(*) FROM documents;

# Check document status progression
SELECT status, count(*) FROM documents GROUP BY status;

# View metadata extracted for a document
SELECT id, source_url, case_number, decision_date, category, status FROM documents LIMIT 10;

# Check pipeline tasks
SELECT document_id, worker, status, error_message FROM pipeline_tasks ORDER BY created_at DESC LIMIT 20;
```

### 2. Check downloaded PDFs

```bash
ls -la ./data/pdfs/
```

### 3. Watch logs

All workers log to stdout. Key things to look for:

- `Crawl complete: years=... tags=N found=X new=Y skipped=Z` — crawl worker summary
- `Downloaded <url>` — successful PDF download
- `Parsed document <id>: <N> chars` — successful text extraction
- `Metadata extracted for <id>` — metadata step complete
- Any `ERROR` lines — failures to investigate

## Resetting State

To re-run the pipeline from scratch:

```bash
# Drop and recreate the database
psql postgresql://postgres:postgres@localhost:5432/overklagan -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Re-apply migrations
uv run alembic upgrade head

# Clear downloaded PDFs
rm -rf ./data/pdfs/*
```

## Running Tests

```bash
# All unit tests (fast, no infra needed)
uv run pytest packages/*/tests/unit/

# Integration tests (requires Postgres running)
uv run pytest packages/*/tests/integration/

# Single package
uv run pytest packages/worker-crawl/tests/
uv run pytest packages/worker-parse/tests/
uv run pytest packages/worker-metadata/tests/
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ValidationError: crawl_api_key` | `CRAWL_API_KEY` not set in `.env` | Add the key to your `.env` — see [CRAWL_SOURCE.md](CRAWL_SOURCE.md) |
| `UnknownYearError: No decision tags found for ...` | Requested a year with no tag upstream | Check the available range in the message; use `--years all` to backfill everything |
| Downloads all fail on a `302` | `follow_redirects` disabled in the download client | Decision URLs redirect to `/filer/...pdf`; the client must follow redirects |
| `Connection refused` on port 5432 | Postgres not running | `docker compose up -d` |
| `relation "documents" does not exist` | Migrations not applied | `uv run alembic upgrade head` |
| `gemini_api_key is required` | `GEMINI_API_KEY` not set | Add key to `.env` (needed for metadata LLM fallback) |
| Crawl finds 0 new documents | All URLs already in DB | Reset state (see above) or use a different source URL |
| Permission denied writing PDFs | `LOCAL_STORAGE_PATH` dir missing | `mkdir -p ./data/pdfs` |
