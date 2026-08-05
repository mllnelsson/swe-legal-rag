---
type: Service
title: Crawl Worker
description: One-shot pipeline entry point — queries the Svenska kyrkan OData API for decisions, deduplicates, and enqueues download tasks.
resource: packages/worker-crawl
tags: [pipeline, worker, crawl, odata]
timestamp: 2026-08-05T00:00:00Z
---

# Crawl Worker (`packages/worker-crawl/`)

One-shot pipeline entry point. Queries the Svenska kyrkan **OData v4 API** for decision
listings, deduplicates against the [documents](/data-model/documents.md) table, and
enqueues download tasks. Full source contract, tag mapping and rationale live in the
[crawl source](/reference/crawl-source.md) reference.

## Why OData rather than HTML scraping

The decision page is now a JS-driven search UI, so the served HTML contains no PDF
anchors and the previous `BeautifulSoup` scraper found nothing. The worker calls the
same OData endpoint the page's own JavaScript uses.

The tag filter in the listing query is **mandatory** — see
[the tag filter is mandatory](/decisions/tag-filter.md).

## Module layout

I/O sits at the edges; year and tag selection are pure functions, unit-tested without
HTTP.

| Module | Role |
|---|---|
| `config.py` | `CrawlSettings(BaseSettings)` — `CRAWL_API_KEY` (required, no default), `CRAWL_YEARS` (default `current`), `CRAWL_API_BASE`, `CRAWL_WEB_ID`, `CRAWL_PAGE_SIZE`, `CRAWL_RATE_LIMIT_DELAY`, `CRAWL_MAX_RETRIES`, `CRAWL_REQUEST_TIMEOUT`, `CRAWL_TOPIC`. `get_crawl_settings()` is `@lru_cache`; `to_odata_config()` maps settings to the `ODataConfig` data object. |
| `odata.py` | HTTP only. `fetch_decision_tags(config)`, `fetch_decisions(config, tag_ids)` (paged via `$skip`/`$top` until `@odata.count`, de-duplicated by document id, retrying 5xx/connect/timeout with exponential backoff), `decision_source_url(config, document_id)`. Module of functions, no client class. |
| `tags.py` | Pure. `parse_tag_index()` groups tags by trailing year; `select_tag_ids()` picks ids for a `YearSelection` and reports unmatched years. |
| `years.py` | Pure. `resolve_years(spec, today)` parses `current` / `all` / `2019` / `2019-2021` / comma-separated mixes. `today` is injected so `current` is testable. |
| `service.py` | `process_crawl(...)` + `CrawlResult` — orchestration. Creates `Document` + two `Task` rows (crawl:completed, download:pending), commits, then publishes. |
| `_protocols.py` | `DecisionSource` Protocol so the `odata` *module* is injected structurally, mirroring the repo-namespace convention. |
| `errors.py` | `CrawlError` and subclasses (`ODataRequestError`, `ODataResponseError`, `YearSpecError`, `UnknownYearError`). |
| `__main__.py` | Entry point with `--years` (overrides `CRAWL_YEARS`). Exits non-zero with a clean message on `CrawlError`. |

## Year selection

Tags are resolved **live** each run, so new decision years work with no code change.
`--years all` additionally pulls the year-less `Överklagandenämndens beslut` tag (125
documents); a default current-year run never does, keeping incremental crawls clean. A
requested year with no tag at all raises `UnknownYearError` rather than silently
reporting an empty crawl.

## Deduplication and idempotency

`get_by_source_url()` is checked before creating a document; `source_url` is the
document-id-keyed `default.aspx?id=...` URL, which is stable across renames. On race
conditions, `IntegrityError` is caught per-document — the session is rolled back and the
document counted as skipped. Since the OData listing supplies a stable `documentId`,
`documents.source_document_id` carries a second unique constraint as a backstop.

**A skipped document publishes nothing**, which is what strands a document whose earlier
run died mid-pipeline: it is already in `documents`, so every later crawl skips it, and
the `pending` task waiting to be re-driven is a message crawl will never send. Re-driving
those is `scripts/run_pipeline.py --resume`'s job, not crawl's — see
[live testing](/playbooks/live-testing.md).

## Transaction ordering and error handling

`process_crawl()` calls `await session.commit()` per document **before** publishing to
the queue, so the download handler (which opens its own session) sees the document as
committed under `QUEUE_BACKEND=sync`; the same ordering keeps rows durable before any
Pub/Sub consumer acts. Per-document errors are caught, logged as warnings, and rolled
back so the crawl never aborts on a single bad document. Listing-level failures (bad API
key, unreachable API, unknown year) raise a `CrawlError` and exit non-zero.
