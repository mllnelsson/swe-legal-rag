---
type: Playbook
title: Live Testing Guide
description: How to run the system locally end-to-end for manual testing and verification, and how to reset state.
tags: [live-testing, pipeline, verification, workflow]
timestamp: 2026-08-13T00:00:00Z
---

# Live Testing Guide

How to run the system locally end-to-end for manual testing and verification.

## Prerequisites

1. Postgres 17 + pgvector running on `localhost:5432`, with the `postgres` role and the
   `overklagan` database — see [local dev](/playbooks/local-dev.md)
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
LOCAL_STORAGE_PATH=./data
QUEUE_BACKEND=sync
EMBEDDING_DIMENSION=1024
LLM_TRACE_ENABLED=true
```

**Which model and provider each task uses is not set here.** It lives in
`llm_config.yaml` at the repo root — see
[llm_config.yaml](/reference/llm-config.md), which is the single source of truth and
carries the full env-var registry. Only secrets belong in `.env`.

This block used to restate the model assignment, and it drifted from the real defaults
once already (see [the log](/log.md)); it is now deliberately short.

To run a task on Gemini instead, give that role `provider: gemini` and a live Gemini
model in `llm_config.yaml` (e.g. `gemini-2.5-flash-lite` — `gemini-2.0-flash` was shut
down, see [LLM pricing](/reference/llm-pricing.md)) and provide `GEMINI_API_KEY`. Set
`embedding.provider: local` for a fully offline embedding path.

Note that `LLM_PROVIDER` in `.env` overrides **every** role's provider and so defeats a
per-role choice; leave it unset unless that is what you want. `ai` logs a warning when
it masks one.

## Pipeline Overview

The ingestion pipeline flows through workers connected by queue topics:

```
crawl → [topic: download] → download → [topic: parse] → parse → [topic: metadata] → metadata → [topic: extract] → extract → chunk → embed
```

With `QUEUE_BACKEND=sync` those topics are one in-process queue, so the whole chain runs
in a single process — see [Option A](#option-a-full-pipeline-sync-queue). See the
[pipeline overview](/pipeline/overview.md) for how the topology and task envelope work.

## Running Workers

### Option A: Full pipeline (sync queue)

With `QUEUE_BACKEND=sync`, publishing appends to one in-process queue that only handlers
subscribed **in the same process** can serve — so the full run is
`scripts/run_pipeline.py`, which subscribes the six downstream workers, runs crawl, and
then pumps the queue crawl filled. Run from the project root:

```bash
# Current year (default)
uv run python scripts/run_pipeline.py

# Backfill the full history (~1073 documents across 2000-2026 plus the year-less tag)
uv run python scripts/run_pipeline.py --years all

# A specific year or range
uv run python scripts/run_pipeline.py --years 2019-2021
```

Running `python -m worker_crawl` on its own does **not** do this. Nothing subscribes in
that process, so the first publish fails with
`QueueHandlerError: No handler registered for topic: 'download'`. Bare crawl is Option B
territory — a single step against a real queue backend.

**A run resumes as well as crawls.** Crawl publishes only for documents it has just
discovered, so anything a previous run left stranded — a document already in
`documents` whose `download` task is still `pending` — is invisible to it: the next
crawl skips the document, and nothing ever sends the message its pending task is waiting
for. Each run therefore queues every `pending` task **before** crawling, which is what
picks those up. `run_pipeline_step` skips tasks that are already `completed`, so
re-driving a finished document costs one no-op per step. Pass `--no-resume` to crawl
only.

Resume has to run before crawl, not after: on the sync backend nothing drains until
`serve()`, so a task crawl has just created is still `pending` and indistinguishable
from one stranded by an earlier run. Resuming afterwards published a second message for
every newly discovered document — 320 `Queue -> download` messages for the 160
documents of the 2020-2026 backfill.

To see what is stranded before running:

```sql
SELECT step, status, count(*) FROM tasks GROUP BY 1, 2 ORDER BY 1, 2;
```

This will:
1. Query the OData API for the current year's decisions
2. Download new PDFs to `./data/documents/`
3. Parse each PDF to extract raw text
4. Extract metadata (rule-based, with LLM fallback)
5. Extract entities and references, chunk, and embed

#### Reading the output

Every step reports itself, so a stalled or skipped stage is visible without querying the
database. Each message produces a queue line carrying the remaining depth, the envelope's
start/finish pair with a duration, and whatever the step itself has to say:

```
21:39:47 INFO    shared.queue.sync: Queue -> parse for document b3101a3d-… (17 behind it)
21:39:47 INFO    shared.pipeline: parse: document b3101a3d-… started
21:39:48 INFO    worker_parse.service: Parsed document b3101a3d-…: 8214 characters from 96431 bytes of PDF
21:39:48 INFO    shared.pipeline: parse: document b3101a3d-… completed in 0.9s -> queued metadata
```

A run ends with the queue's own tally and a `tasks` count by step and status — the same
breakdown as the stranded-work query above, without opening `psql`:

```
21:52:03 INFO    shared.queue.sync: Queue drained: 618 message(s) dispatched, 2 failed, 0 left
21:52:03 INFO    run_pipeline: Pipeline run finished in 743.2s
21:52:03 INFO    run_pipeline: Task status by step:
21:52:03 INFO    run_pipeline:   download  pending=0  processing=0  completed=103  failed=0
21:52:03 INFO    run_pipeline:   parse     pending=0  processing=0  completed=102  failed=1
```

A step whose `completed` count is short of the one above it is where documents were lost;
`failed` names the step to investigate, and `tasks.error_message` carries the reason. See
[worker patterns](/pipeline/worker-patterns.md) for the full set of lines.

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
`chunk` calls the configured LLM provider (Berget by default, or Gemini); `embed` calls
the configured embedding provider (Berget by default, or the local e5 model with
`EMBEDDING_PROVIDER=local` — no API, no DB). `metadata` reaches no model here — the
script injects `worker_metadata.service.no_llm_extractor`, so only its rule-based pass
runs, unlike the worker. `extract` reaches one only when `EXTRACT_STRATEGY` asks it to.
`--store fs` synthesizes a throwaway `DATABASE_URL` when none is set, so it works with
no `.env` database config.

#### Running with no LLM at all

Useful for iterating on crawling, parsing and rule-based extraction without a key, a
bill, or a network round-trip per document:

```bash
export LLM_PROVIDER=none          # every role resolves to a provider that refuses
export EXTRACT_STRATEGY=rule_based

uv run python scripts/run_step.py crawl --years 2024
uv run python scripts/run_step.py docs                       # pick a document id
uv run python scripts/run_step.py chain <doc_id> --until extract
```

All five tasks reach `completed`. Going one step further —
`chain <doc_id> --until chunk` — leaves the chunk task `failed` with
`LLMDisabledError` in `error_message`: the summary is prepended to every chunk, so
chunk is where a no-LLM run stops. This works for the workers too
(`python -m worker_metadata`, `scripts/run_pipeline.py`), which otherwise refuse to
start without a key. See [running with no LLM](/reference/llm-config.md) for what each
step does and how to disable a single role instead of all of them.

### Option D: LLM task runner (`scripts/run_agent.py`)

The LLM-side counterpart to `scripts/run_step.py` above: `run_step.py` batches the
ingestion pipeline one document at a time, this batches an LLM task one input at a time.
An input file holds one input per line; the lines run in sequence; each input's output is
appended to a JSONL file as it completes, so a run killed part-way keeps what it had.
Change a prompt, re-run the same file, and the two runs are directly comparable.

```bash
uv run python scripts/run_agent.py sql       questions.txt
uv run python scripts/run_agent.py chat      questions.txt
uv run python scripts/run_agent.py summarize decisions.txt
uv run python scripts/run_agent.py sql       questions.txt --limit 3    # cheap smoke run
uv run python scripts/run_agent.py sql       questions.txt --out data/runs/before.jsonl
```

Three tasks today: `sql` (the [SQL agent](/api/sql-agent.md)), `chat` (the
[conversational agent](/retrieval/chat-agent.md)) and `summarize` (worker-chunk's
summariser). All sit behind a small registry, so a fourth task already implemented in
`ai.services` (`expand_query`, `extract_metadata`) is one preparer function away, not a
rewrite.

`chat` runs the whole agent — the tool loop, both sub-agents and the streamed synthesis
— and records the answer, the sources, any SQL it ran, **and the tool trail** (`steps`:
the tool and progress label of every call it made). The trail is there because most of
what goes wrong in an agent run shows up in which tools it reached for rather than in
the prose: a run that never called `list_vocabulary` and then filtered on a category, or
one that answered a counting question without `query_corpus`, is visible at a glance.
It is also the most expensive task here by a wide margin — one line is a full agent run,
so `--limit 3` first.

**What a line means is the task's own business.** `sql` and `chat` take one question per
line; `summarize` takes one *path* to a decision text file per line — a whole decision
body cannot be a line of a text file. Each task states its own answer at registration, and
`--help` renders it. Blank lines and `#` comments are skipped, so a curated question set
can carry section headings; the record still keeps the file's original line number
(`source_line`), because case 7 is rarely line 7.

**A failing case is recorded, not aborted.** A case that raises is caught, logged with
its error, and the run moves on to the next input — that is the whole point of a batch
runner. `Exception`, not `BaseException`, so Ctrl-C still stops the run outright. Exit
code is 1 if any case failed, 0 otherwise — the same convention as
`scripts/check_semantic_model.py`.

**`ok` is not `answered`.** `ok` means the call completed. The SQL agent never raises for
a question it cannot answer — it comes back `answered: false` with a reason (see
[the endpoint's never-500s semantics](/api/sql-agent.md#never-500s)) — so a record can
perfectly well be `ok: true` with `output.answered: false`. Reading that as a crash is
the one mistake this format invites.

**The prompt and the token counts are not duplicated into the record.** Every case runs
inside its own `trace_context(run_id=..., case=...)`, so the full prompt, response and
usage for any line are one grep away in the trace stream by `context.run_id` and
`context.case` — see
[the correlation table](/observability.md#correlation--the-wiring-invariant). This is
why the JSONL record itself stays small.

The `sql` task calls `agents.check_semantic_model()` once, before running a single case
— the same check the API makes fatal at startup, paid here before the first billed call
rather than after twenty. The `summarize` task measures against
`shared.segmentation.split_document(...).body`, exactly what worker-chunk summarises —
the pipeline never summarises the appendices, so feeding the whole file would tune a
prompt input production never sends. It reports `summary_tokens` (counted with the same
`ai.create_embedding_ruler()` tokenizer worker-chunk uses) against
`worker_chunk.budget.SUMMARY_RESERVE_TOKENS`; `within_reserve: false` means worker-chunk
would truncate this summary — the signal to watch when iterating on the summarisation
prompt.

The database is whatever `DATABASE_URL` says, like the rest of the app — no override
flag. `summarize` never opens it.

**Output:** one JSONL file per run, `data/agent-runs/<task>-<run_id>.jsonl` by default
(`data/` is gitignored, same as `run_step.py --store fs`'s output; `--out` names it
explicitly). Every record carries `run_id` and `task`, so a line is self-describing with
no separate manifest to read:

```json
{"schema_version": 1, "run_id": "20260809T142530Z", "task": "sql",
 "index": 1, "source_line": 4, "input": "Hur många överklaganden avslogs 2026?",
 "started_at": "2026-08-09T14:25:31Z", "latency_ms": 8123,
 "ok": true, "error": null,
 "output": {"answered": true, "sql": "SELECT …", "rows": [[12]], "…": "…"}}
```

For `summarize`, `input` holds the file *path*, not the decision text — the text stays
in the file it came from — and `output` carries `summary`, `summary_tokens`,
`reserve_tokens`, `within_reserve`, `input_chars`, `body_chars`.

**Smoke-testing the harness itself, with no key and no billed call:**

```bash
LLM_PROVIDER=none uv run python scripts/run_agent.py sql questions.txt
```

Every input records `ok: false` with `error.type: "LLMDisabledError"`, one line per
input, exit code 1 — the loop, the per-case error capture, the flushing and the exit code
all exercised offline.

**Not in scope.** No scoring — no expected answers, no pass/fail, no diffing between
runs; the record is what makes those possible later, this script only records it. No
concurrency — inputs run strictly in sequence. No cost computed, for the same reason
[observability](/observability.md) never computes one: apply a rate to `usage` in the
matching trace records instead.

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
ls -la ./data/documents/
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
ls data/llm-traces/$(date -u +%F)/
cat data/llm-traces/$(date -u +%F)/*.jsonl | wc -l

cat data/llm-traces/$(date -u +%F)/*.jsonl \
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
cat data/llm-traces/$(date -u +%F)/*.jsonl \
  | jq -r --arg i "<uuid>" 'select(.context.interaction_id == $i)
      | [.context.source, .model, .usage.input_tokens,
         .usage.output_tokens] | @tsv'
```

Expect one call per tool-loop iteration under `agents.chat`, plus `ai.embed`,
`ai.synthesize_answer`,
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

# Clear downloaded PDFs and traces — both sit directly under the storage root
rm -rf ./data/documents/* ./data/llm-traces/*
```

> Copy `data/llm-traces/` first if the cost history from the run matters — nothing else
> holds it. `data/store/` (`run_step.py --store fs`) and `data/agent-runs/`
> (`run_agent.py`) are separate and untouched by this.

## Re-embedding after an embedding-config change

Stored vectors are only comparable to queries embedded the same way. Changing any of
`embedding.model`, `embedding.query_prefix` or `embedding.passage_prefix` in
[`llm_config.yaml`](/reference/llm-config.md) **invalidates every stored embedding** —
retrieval keeps working, silently and badly, so nothing will tell you.

This is not hypothetical: the `passage_prefix` was previously never applied even though
queries were prefixed, so any corpus embedded before that fix must be rebuilt.

```bash
# 1. Clear the vectors, keeping documents, chunks and everything upstream
psql "$DATABASE_URL" -c "UPDATE chunks SET embedding = NULL;"

# 2. Reset the embed task so the step will run again
psql "$DATABASE_URL" -c "UPDATE tasks SET status = 'pending', error_message = NULL, started_at = NULL, completed_at = NULL WHERE step = 'embed';"

# 3. Re-run the embed step for each document
uv run python scripts/run_step.py docs                 # list document ids
uv run python scripts/run_step.py embed <document_id>  # once per document
```

Then confirm: `SELECT count(*) FROM chunks WHERE embedding IS NULL;` should be `0`, and a
query that previously returned a known document should still return it. A change in
`embedding.dimension` additionally requires a migration recreating the `chunks.embedding`
column at the new width — see
[embedding dimension](/decisions/embedding-dimension.md).

## Running Tests

```bash
# Unit tests — the default. Fast, hermetic, needs no infrastructure.
uv run pytest

# Integration tests alone. Needs Postgres and the overklagan_test database.
uv run pytest -m integration

# Everything.
uv run pytest -m ""

# Single package
uv run pytest packages/worker-crawl/tests/
uv run pytest packages/worker-parse/tests/
uv run pytest packages/worker-metadata/tests/
```

Integration tests run against `overklagan_test`, never the `overklagan` database this
playbook fills — so a test run cannot destroy a live pipeline corpus, and a
misconfigured `TEST_DATABASE_URL` aborts the run rather than truncating.

See the [testing strategy](/testing.md) for the full unit/integration split.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ValidationError: crawl_api_key` | `CRAWL_API_KEY` not set in `.env` | Add the key to your `.env` — see [crawl source](/reference/crawl-source.md) |
| `UnknownYearError: No decision tags found for ...` | Requested a year with no tag upstream | Check the available range in the message; use `--years all` to backfill everything |
| Downloads all fail on a `302` | `follow_redirects` disabled in the download client | Decision URLs redirect to `/filer/...pdf`; the client must follow redirects |
| `Connection refused` on port 5432 | Postgres not running | `docker compose up -d db` (Linux) or `brew services start postgresql@17` (macOS) |
| `role "postgres" does not exist` | macOS only — Homebrew's initdb made your macOS user the superuser | `createuser -s postgres` — see [local dev](/playbooks/local-dev.md) |
| `psql: command not found` | macOS only — `postgresql@17` is keg-only, so its `bin` is not linked onto `PATH` | Add `$(brew --prefix)/opt/postgresql@17/bin` to `PATH` in your shell profile |
| `relation "documents" does not exist` | Migrations not applied | `uv run alembic upgrade head` |
| `database "overklagan_test" does not exist` on `-m integration` | The test database was never created | `createdb -O postgres overklagan_test` — see [local dev](/playbooks/local-dev.md) |
| `Integration tests would run against the development database` | `TEST_DATABASE_URL` names the same database as `DATABASE_URL` | Unset it to use the derived `_test` default, or point it elsewhere. Nothing was truncated |
| `berget_api_key is required` (or `gemini_api_key is required`) | LLM/embedding provider key not set | Add `BERGET_API_KEY` (default provider) — or `GEMINI_API_KEY` if `LLM_PROVIDER=gemini` — to `.env` |
| Crawl finds 0 new documents | All URLs already in DB | Reset state (see above) or use a different source URL |
| Permission denied writing PDFs | `LOCAL_STORAGE_PATH` dir missing | `mkdir -p ./data` |
