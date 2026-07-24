---
type: Service
title: Download Worker
description: Subscriber worker that fetches PDFs from source URLs, stores them via the storage backend, and enqueues parse tasks.
resource: packages/worker-download
tags: [pipeline, worker, download, storage]
timestamp: 2026-07-24T00:00:00Z
---

# Download Worker (`packages/worker-download/`)

Long-running subscriber. Consumes document IDs from the download topic, fetches PDFs,
stores them via the [storage backend](/packages/shared.md), updates the
[document](/data-model/documents.md) record, and enqueues parse tasks. Storage key
format: `documents/{document_id}/original.pdf`.

## Module layout

| Module | Role |
|---|---|
| `config.py` | `DownloadSettings(BaseSettings)` — `DOWNLOAD_REQUEST_TIMEOUT` (60s), `DOWNLOAD_TOPIC` (`download`), `DOWNLOAD_NEXT_TOPIC` (`parse`), `DOWNLOAD_MAX_RETRIES` (3), `DOWNLOAD_RATE_LIMIT_DELAY` (0.5s). `get_download_settings()` is `@lru_cache`. |
| `service.py` | `process_download(message, *, session, document_repo, task_repo, storage, queue_publisher, timeout, max_retries, rate_limit_delay, next_topic)` async function + module-level `_download_pdf()` helper. No class. The body runs inside `shared.pipeline.run_pipeline_step`. |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, registers the handler, installs signal handlers, calls `subscriber.start()`. The handler wraps `asyncio.run()` around `process_download()` for the sync `QueueSubscriber` protocol. |

## Download with retry

`_download_pdf(url, timeout, max_retries) -> bytes` is a module-level function. It
creates an `httpx.Client` and attempts up to `max_retries` times with exponential
backoff (`2**attempt` seconds). HTTP 4xx responses raise immediately (not retryable);
5xx, connection errors, and timeouts are retried. Decision URLs 302-redirect to the real
`/filer/...pdf` path, so the client must set `follow_redirects=True` (see
[crawl source](/reference/crawl-source.md)). A `rate_limit_delay` sleep follows each
successful download.

## Idempotency

Multiple guard layers: (1) task status check — if already `completed`, skip; (2)
`document.gcs_uri` check — if already set, skip the download but still create the parse
task and publish; (3) storage `store()` is overwrite-safe (same key → same result); (4)
the `(document_id, step)` unique constraint prevents duplicate task creation.

## Checkpointing, ordering, error handling

Task lifecycle, commit-before-publish, session-per-message, and failure handling are all
owned by the shared task envelope — see [worker patterns](/pipeline/worker-patterns.md).
Download leaves `reraise` at its default `False`, so one failed message does not affect
others.
