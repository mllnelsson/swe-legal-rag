---
type: Reference
title: Crawl Source — Svenska kyrkan OData API
description: Authoritative reference for where Överklagandenämnden decisions come from and why the crawl worker is shaped the way it is.
resource: https://www.svenskakyrkan.se/webapi/api-v3/odata/
tags: [crawl, odata, source, svenska-kyrkan]
timestamp: 2026-07-24T00:00:00Z
---

# Crawl Source — Svenska kyrkan OData API

Authoritative reference for where Överklagandenämnden decisions come from and why the
crawl worker is shaped the way it is. Read before touching `packages/worker-crawl/` (see
also the [crawl worker](/pipeline/crawl.md) concept).

## Why this replaced HTML scraping

The crawler originally fetched a decision listing page and collected `<a href="*.pdf">`
anchors. svenskakyrkan.se now renders that page as a JS-driven search UI backed by an
OData API, so the served HTML contains **no PDF anchors** and the scraper found nothing.
The worker now queries the same API the page's own JavaScript calls.

## The API

**OData v4** (OASIS Open Data Protocol), served by an ASP.NET Web API OData endpoint
over the CMS. Confirmed from `$metadata`:

```xml
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <Schema Namespace="SvenskaKyrkan.Contracts.V2.ExtensionsDb.Models">
```

- **Service root**: `https://www.svenskakyrkan.se/webapi/api-v3/odata/`
- **Auth**: `apikey` query parameter. Anonymous — no login is involved.
- **Query options**: `$filter $select $expand $top $skip $orderBy $count`
- **Schema**: `GET $metadata` returns CSDL/EDMX. ~30 entity sets; the crawler uses
  `documents` and `tags`.
- Responses carry `@odata.count` (total matching rows, independent of `$top`), which is
  what drives pagination.

### API key

`CRAWL_API_KEY` is a **required setting with no default in code**. The working key is
the client-side one the public decision search sends from a logged-out browser; read it
from the site's own network requests.

**Design decision:** it is not committed, even though it is very likely public. Its
provenance was never fully verified (it does not appear in the served HTML of
`/overklagandenamnden`; the JS bundles were not checked). Keeping it in the environment
costs nothing if it is public, and if it turns out to be scoped or rotatable no code
change or git-history rewrite is needed.

## The document filter

```
published eq true
  and sqlDocumentType in('F')
  and webId in (1374643)
  and tags/any(t: t/databaseId in (<tag ids>))
```

The `tags/any(...)` clause is **mandatory** — without it the query returns every binary
file on the web rather than the decision corpus. See
[the tag filter is mandatory](/decisions/tag-filter.md) for the rationale and the row
counts.

## Decision tags

Decisions are scoped by tag, one tag per decision year, discovered at runtime via:

```
GET /odata/tags?$filter=startswith(name,'Överklagandenämndens beslut')
```

Resolving tags live means new years (2027…) work with **no code change**. The table
below is a snapshot for reference and for the test fixture in
`packages/worker-crawl/tests/unit/test_tags.py` — it is not the lookup source.

| Year | databaseId | Note |
|---|---|---|
| 2000 | 760868 | |
| 2001 | 760869 | |
| 2002 | 760870 | |
| 2003 | 760871 | |
| 2004 | 760872 | |
| 2005 | 760873 | |
| 2006 | 760874 | |
| 2007 | 760875 | |
| 2008 | 760876 | |
| 2009 | 760877 | |
| 2010 | 760878 | |
| 2011 | 760879 | |
| 2012 | 855857 | |
| 2013 | 100007427 | duplicate tag, 0 documents |
| 2013 | 100007428 | 39 documents |
| 2014 | 100013243 | |
| 2015 | 100019713 | |
| 2016 | 100024478 | |
| 2017 | 100065189 | id higher than 2019's |
| 2018 | 100064820 | |
| 2019 | 100064819 | |
| 2020 | 100064821 | |
| 2021 | 100067925 | |
| 2022 | 100082126 | |
| 2023 | 100092236 | name starts with a **lowercase** `ö` |
| 2024 | 100100768 | |
| 2025 | 100104828 | 21 documents |
| 2026 | 100112325 | 25 documents |
| *(none)* | 760887 | `Överklagandenämndens beslut` — 125 documents, no year |

### Three traps the code must survive

1. **A year can map to several tag ids.** 2013 has two. `TagIndex.by_year` therefore
   holds a *tuple* of ids per year, never a single id.
2. **Ids are not chronological.** 2017 (`100065189`) is higher than 2019
   (`100064819`), so an id can never be derived arithmetically from a year — it must be
   looked up.
3. **Casing is inconsistent.** The 2023 tag is lowercase. OData's `startswith` is
   case-insensitive (which is why that tag is reachable at all), and year parsing on our
   side matches on the trailing four digits, never on name casing.

### The year-less tag

Tag `760887` carries 125 documents belonging to no single year. **Design decision:** it
is included only under `--years all`, never in a routine current-year run, so
incremental crawls stay clean while a full backfill still reaches the whole corpus. It
is exposed separately as `TagIndex.undated`.

## Document identity and download URL

`documents.source_url` stores the canonical, document-id-keyed URL:

```
https://www.svenskakyrkan.se/default.aspx?id={documentId}&ptid=
```

Chosen over the `attachmentFileName` path (`filer/1374643/Beslut 2025-21 ....pdf`)
because it is stable when a file is renamed and needs no URL-encoding of spaces and
Swedish characters. It **302-redirects** to the real `/filer/...pdf` path — which is why
the [download worker](/pipeline/download.md) must set `follow_redirects=True`. httpx
defaults that to `False` and `raise_for_status()` rejects an unfollowed redirect, so
without it every download fails on a 302.

The listing also yields `documentId`, `headline` and `publishDate`, persisted as
`source_document_id` (unique), `source_headline` and `source_published_at`. See the
[documents table](/data-model/documents.md).

## Module layout

I/O is kept at the edges; the selection logic is pure and unit-tested without HTTP.

| Module | Responsibility |
|---|---|
| `odata.py` | HTTP only: `fetch_decision_tags`, `fetch_decisions` (paging + retry), `decision_source_url` |
| `tags.py` | Pure: `parse_tag_index`, `select_tag_ids` — the three traps live here |
| `years.py` | Pure: `resolve_years` parses `current` / `all` / `2019` / `2019-2021` |
| `service.py` | Orchestration: persist documents, create tasks, publish |
| `errors.py` | `CrawlError` and subclasses |

## Operational notes

- **Pagination**: `$skip`/`$top` at `CRAWL_PAGE_SIZE` until `@odata.count` is reached,
  with a `MAX_PAGES` cap so an upstream count bug cannot spin forever. Results are
  de-duplicated by document id, because `$orderBy=publishdate desc` is not a unique sort
  and a row can repeat across page boundaries.
- **Retry**: 5xx, connect and timeout errors retry with exponential backoff; 4xx is
  raised immediately.
- **Rate limiting**: `CRAWL_RATE_LIMIT_DELAY` seconds between pages; requests identify
  themselves via a `church-legal-db-crawler/0.2` User-Agent.
