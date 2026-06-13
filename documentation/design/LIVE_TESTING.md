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
# Must set — no default
CRAWL_SOURCE_URL=https://www.svenskakyrkan.se/beslut-fran-overklagandenamnden

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
EMBEDDING_MODEL=e5-multilingual
EMBEDDING_DIMENSION=768
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
uv run --package worker-crawl python -m worker_crawl
```

This will:
1. Crawl the source URL for PDF links
2. Download new PDFs to `./data/pdfs/`
3. Parse each PDF to extract raw text
4. Extract metadata (rule-based, with LLM fallback)

### Option B: Individual workers (for debugging)

Run each worker as a separate process. Useful when `QUEUE_BACKEND` is not `sync` or to isolate a single step:

```bash
# Crawl — discovers PDF links, publishes to 'download' topic
uv run --package worker-crawl python -m worker_crawl

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

- `Crawl complete: found=X new=Y skipped=Z` — crawl worker summary
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
| `ValidationError: crawl_source_url` | `CRAWL_SOURCE_URL` not set in `.env` | Add the URL to your `.env` |
| `Connection refused` on port 5432 | Postgres not running | `docker compose up -d` |
| `relation "documents" does not exist` | Migrations not applied | `uv run alembic upgrade head` |
| `gemini_api_key is required` | `GEMINI_API_KEY` not set | Add key to `.env` (needed for metadata LLM fallback) |
| Crawl finds 0 new documents | All URLs already in DB | Reset state (see above) or use a different source URL |
| Permission denied writing PDFs | `LOCAL_STORAGE_PATH` dir missing | `mkdir -p ./data/pdfs` |
