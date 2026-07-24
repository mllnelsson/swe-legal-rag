---
type: Decision
title: The crawl tag filter is mandatory
description: Why the crawl query must filter on decision tags — without it the API returns every binary file on the web, not the decision corpus.
tags: [crawl, odata, filtering, corpus]
timestamp: 2026-07-24T00:00:00Z
---

# The crawl tag filter is mandatory

**Status:** Accepted

The [crawl worker](/pipeline/crawl.md) queries the Svenska kyrkan
[OData API](/reference/crawl-source.md) for decisions. Its `$filter` **must** include
the decision-tag clause:

```
tags/any(t: t/databaseId in (<tag ids>))
```

## Why

Dropping the tag clause does not widen the result to "all decisions" — it widens it to
every binary file published on that web:

| Filter | Rows |
|---|---|
| Without the tag clause | **5039** — posters, ad creatives, kyrkostyrelsen protocols, annual reports |
| With all decision tags | **1073** — the actual decision corpus |

A date filter (`publishDate ge <ISO>`) is accepted by the API but is **not** a
substitute: it cannot tell a decision apart from a poster published the same week. The
tag identity is the only signal that distinguishes a decision from any other file.

## Consequence

The tag clause is therefore never optional in a crawl query, and the tag ids it
references are resolved live per year — see
[crawl source](/reference/crawl-source.md) for how tags are discovered and the data
traps that resolution must survive.
