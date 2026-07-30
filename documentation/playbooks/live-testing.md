---
type: Playbook
title: Live Testing Guide
description: How to run the system locally end-to-end for manual testing and verification, and how to reset state.
tags: [live-testing, pipeline, verification, workflow]
timestamp: 2026-07-27T00:00:00Z
---

# Live Testing Guide

How to run the system locally end-to-end for manual testing and verification.

## Prerequisites

1. Docker running (`docker compose up -d` — starts Postgres with pgvector)
2. Dependencies installed: `uv sync --all-packages`
3. Environment configured: `cp .env.example .env` and edit values (see below)
4. Migrations applied: `uv run alembic upgrade head`

## Required Environment Variables

Edit `.env` before running. Minimum required for a full pipeline run, using the default
Berget provider (matches [local dev](/playbooks/local-dev.md)):

```bash
# Must set — no default. Client-side key used by the public decision search on
# svenskakyrkan.se; read it from the site's own network requests.
# See /reference/crawl-source.md
CRAWL_API_KEY=<api-key>

# Which decision years to crawl: current (default) | all | 2019 | 2019-2021
CRAWL_YEARS=current

# Must set — Berget is the default LLM + embedding provider. Used by the metadata LLM
# fallback, worker-chunk summaries, and worker-embed.
BERGET_API_KEY=<your-key>

# Defaults are fine for local dev
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/overklagan
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./data/pdfs
QUEUE_BACKEND=sync
LLM_PROVIDER=berget
LLM_MODEL_STRUCTURED=mistralai/Mistral-Small-3.2-24B-Instruct-2506
LLM_MODEL_SUMMARIZE=mistralai/Mistral-Medium-3.5-128B
LLM_MODEL_CHAT=zai-org/GLM-5.2
EMBEDDING_PROVIDER=berget
EMBEDDING_MODEL=intfloat/multilingual-e5-large
EMBEDDING_DIMENSION=1024
LLM_TRACE_ENABLED=true
```

To run on Gemini instead, set `LLM_PROVIDER=gemini`, provide `GEMINI_API_KEY`, and set
the three `LLM_MODEL_*` vars to valid live Gemini models (e.g. `gemini-2.5-flash-lite` —
`gemini-2.0-flash` was shut down, see [LLM pricing](/reference/llm-pricing.md)). Set
`EMBEDDING_PROVIDER=local` for a fully offline embedding path.

## Pipeline Overview

The ingestion pipeline flows through workers connected by queue topics:

```
crawl → [topic: download] → download → [topic: parse] → parse → [topic: metadata] → metadata → [topic: extract] → extract → chunk → embed
```

With `QUEUE_BACKEND=sync`, each worker dispatches to the next inline — you can run the
full pipeline in sequence. See the [pipeline overview](/pipeline/overview.md) for how
the topology and task envelope work.

## Running Workers

### Option A: Full pipeline (sync queue)

With `QUEUE_BACKEND=sync`, the crawl worker triggers download inline, which triggers
parse, which triggers metadata, and so on through embed. Run from the project root:

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
5. Extract entities and references, chunk, and embed

### Option B: Individual workers (for debugging)

Run each worker as a separate process. Useful when `QUEUE_BACKEND` is not `sync` or to
isolate a single step. All seven workers (`crawl`, `download`, `parse`, `metadata`,
`extract`, `chunk`, `embed`) are implemented and runnable:

```bash
# Crawl — discovers decisions via the OData API, publishes to 'download' topic
uv run --package worker-crawl python -m worker_crawl [--years all]

# Download — listens on 'download', saves PDFs, publishes to 'parse'
uv run --package worker-download python -m worker_download

# Parse — listens on 'parse', extracts text, publishes to 'metadata'
uv run --package worker-parse python -m worker_parse

# Metadata — listens on 'metadata', extracts structured fields, publishes to 'extract'
uv run --package worker-metadata python -m worker_metadata

# Extract — entity & reference extraction, publishes to 'chunk'
uv run --package worker-extract python -m worker_extract

# Chunk — contextual chunking, publishes to 'embed'
uv run --package worker-chunk python -m worker_chunk

# Embed — embedding generation and indexing
uv run --package worker-embed python -m worker_embed
```

### Option C: Per-step runner (`scripts/run_step.py`)

For hand-testing one stage at a time — iterate on a step over a single document, inspect
what it produced, tweak the code, re-run — use the per-step runner. It calls each
worker's service function directly with a no-op queue publisher, so a step runs and then
**stops** instead of cascading to the next (which is what the `sync` queue does in a
single process). Re-running a step is safe: the current step's task is reset to
`pending` and the immediate downstream task row is cleared first (avoids the
`uq_tasks_document_id_step` unique violation).

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

Steps do **not** pass a single JSON to each other. They communicate through the **shared
store**, which accumulates: `parse` writes `documents.json[].raw_text`, `metadata` fills
the structured fields on the same row, `extract` writes `entities.json` /
`references.json`, `chunk` writes `chunks.json`, and so on. So "the JSON from the
previous step" is just the store on disk after that step ran.

That means you can start at any step as long as the store already holds its inputs (e.g.
`extract` needs a document with `raw_text`; `case_number` is optional). Two ways to get
there:

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
`case_number`, `decision_date`, `summary`, `decision_outcome`, `category`, `gcs_uri`);
unknown keys are ignored with a warning. Keep a library of input fixtures by pointing
`--store-dir` at different folders.

#### DB-free playground (`--store fs`)

Add `--store fs` to **any** of the commands above to run against JSON files under
`./data/store/` (override with `--store-dir`) instead of Postgres — no database, no
migrations, nothing dumped into the DB. The real worker services run unchanged; only the
injected **repo namespaces** are swapped — the real `shared.repositories.*` modules are
replaced by the file-backed doubles in `scripts/_fsrepos/*` (backed by
`scripts/_fsstore.py`). Both satisfy the same `shared.repositories._protocols`
interfaces, so no worker code changes between DB and fs modes (see
[repositories](/data-model/repositories.md)). Each table is a JSON file of the pydantic
DTOs (`documents.json`, `tasks.json`, `chunks.json`, `entities.json`,
`document_entities.json`, `references.json`, `unresolved.json`); PDFs still land under
`LOCAL_STORAGE_PATH` via the local storage backend. `commit()` writes the JSON,
`rollback()` reloads it, so transaction/rollback behaviour matches the DB.

```bash
uv run python scripts/run_step.py --store fs crawl
uv run python scripts/run_step.py --store fs parse <doc_id>
cat ./data/store/documents.json    # inspect the raw_text the parser produced
```

Per-step external dependencies (same in both stores): `crawl`/`download` need network;
`metadata` and `chunk` call the configured LLM provider (Berget by default, or Gemini);
`embed` calls the configured embedding provider (Berget by default, or the local e5
model with `EMBEDDING_PROVIDER=local` — no API, no DB). `--store fs` synthesizes a
throwaway `DATABASE_URL` when none is set, so it works with no `.env` database config.

## Running the API Server

```bash
uv run --package api uvicorn api.main:app --reload --port 8000
```

Exposes `GET /health` and the chat endpoint [`POST /api/chat`](/api/chat-endpoint.md)
(SSE).

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
SELECT document_id, step, status, error_message FROM tasks ORDER BY created_at DESC LIMIT 20;
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

## Verifying LLM Traces

With `LLM_TRACE_ENABLED=true`, every LLM and hosted-embedding call lands in a daily
directory of batched JSONL objects. After a pipeline run:

```bash
ls data/pdfs/llm-traces/$(date -u +%F)/
cat data/pdfs/llm-traces/$(date -u +%F)/*.jsonl | wc -l

cat data/pdfs/llm-traces/$(date -u +%F)/*.jsonl \
  | jq -r '[.operation, .context.source, .model,
            .usage.total_tokens, .success] | @tsv' | head
```

Expect a **small number** of `.jsonl` objects — records are batched, so this is nowhere
near one file per call — at least one record per LLM-using worker that fired, a non-null
`model` and `usage.total_tokens` on each, and `success` true.

> **Cost is answered in tokens, not currency.** No rate table lives in this repo and no
> Berget rate is published here (see [LLM pricing](/reference/llm-pricing.md)). The
> records carry `model` and `usage`; pricing them is an analysis step, and a rate
> obtained later applies to these same records.

To cost a single chat question, start the API, send one message, and note the
`Chat interaction <uuid> for session …` line in the API log:

```bash
cat data/pdfs/llm-traces/$(date -u +%F)/*.jsonl \
  | jq -r --arg i "<uuid>" 'select(.context.interaction_id == $i)
      | [.context.source, .model, .usage.input_tokens,
         .usage.output_tokens] | @tsv'
```

Expect at least four calls — `ai.decompose_query`, `ai.embed`, `ai.synthesize_answer`,
plus `api.retriever.rerank` when reranking is on.

Closing the browser tab mid-answer should still leave an `ai.synthesize_answer` record,
with `success: false`, `error.type` `GeneratorExit`, and the partial text that had been
delivered. Full schema and query recipes: [LLM Observability](/observability.md).

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

> This also wipes `data/pdfs/llm-traces/`, since traces share the storage root. Copy
> that directory first if the cost history from the run matters — nothing else holds it.

## Running Tests

```bash
# All unit tests (fast, no infra needed)
uv run pytest -m "not integration"

# Integration tests (requires Postgres running)
uv run pytest -m integration

# Single package
uv run pytest packages/worker-crawl/tests/
uv run pytest packages/worker-parse/tests/
uv run pytest packages/worker-metadata/tests/
```

See the [testing strategy](/testing.md) for the full unit/integration split.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ValidationError: crawl_api_key` | `CRAWL_API_KEY` not set in `.env` | Add the key to your `.env` — see [crawl source](/reference/crawl-source.md) |
| `UnknownYearError: No decision tags found for ...` | Requested a year with no tag upstream | Check the available range in the message; use `--years all` to backfill everything |
| Downloads all fail on a `302` | `follow_redirects` disabled in the download client | Decision URLs redirect to `/filer/...pdf`; the client must follow redirects |
| `Connection refused` on port 5432 | Postgres not running | `docker compose up -d` |
| `relation "documents" does not exist` | Migrations not applied | `uv run alembic upgrade head` |
| `berget_api_key is required` (or `gemini_api_key is required`) | LLM/embedding provider key not set | Add `BERGET_API_KEY` (default provider) — or `GEMINI_API_KEY` if `LLM_PROVIDER=gemini` — to `.env` |
| Crawl finds 0 new documents | All URLs already in DB | Reset state (see above) or use a different source URL |
| Permission denied writing PDFs | `LOCAL_STORAGE_PATH` dir missing | `mkdir -p ./data/pdfs` |
