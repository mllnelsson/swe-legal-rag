---
type: Concept
title: Ingestion Pipeline Overview
description: The queue-driven ingestion topology — seven Cloud Run workers connected by Pub/Sub topics, each checkpointing its output for resumability.
tags: [pipeline, ingestion, queue, architecture]
timestamp: 2026-07-24T00:00:00Z
---

# Ingestion Pipeline Overview

Queue-driven (Pub/Sub), each step is a Cloud Run worker consuming from a topic and
publishing to the next. Each step checkpoints its output so failures are resumable.

```
crawl → [download] → download → [parse] → parse → [metadata] → metadata → [extract] → extract → [chunk] → chunk → [embed] → embed
```

| Step | Worker | What it does |
|---|---|---|
| 1 | [crawl](/pipeline/crawl.md) | Query the OData API, dedup, enqueue downloads |
| 2 | [download](/pipeline/download.md) | Fetch PDFs, store via the storage backend |
| 3 | [parse](/pipeline/parse.md) | PDF → raw text (pypdfium2) |
| 4 | [metadata](/pipeline/metadata.md) | Rule-based + LLM-fallback structured metadata |
| 5 | [extract](/pipeline/extract.md) | Entities & cross-references (graph-in-Postgres) |
| 6 | [chunk](/pipeline/chunk.md) | Summary + contextual, token-bounded chunks |
| 7 | [embed](/pipeline/embed.md) | Vector embeddings + index (terminal step) |

Each queue message maps 1:1 to a [task](/data-model/tasks.md) row, and each step fills
its own columns on the [documents](/data-model/documents.md) row — so the two tables
together give full ingestion observability.

## Two worker patterns

- **One-shot workers** (crawl): run once, process all items, exit. Launched by Cloud
  Scheduler via Cloud Run Jobs. The entry point calls `asyncio.run()`, logs the result,
  then exits.
- **Subscriber workers** (download … embed): register a queue handler and block on
  messages. Suitable for Cloud Run triggered by Pub/Sub push. The entry point installs
  signal handlers and calls `subscriber.start()`.

All subscriber workers share one task envelope and a set of conventions (session-per-
message, commit-before-publish) — see [worker patterns](/pipeline/worker-patterns.md).
Crawl is not a pipeline step in that sense: it loops over many listings producing many
documents and tasks, so it keeps its own per-document loop.

Locally the whole chain runs in a single process with `QUEUE_BACKEND=sync` — see
[live testing](/playbooks/live-testing.md).
