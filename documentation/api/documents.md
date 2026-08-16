---
type: API Endpoint
title: Documents Endpoint (GET /api/documents)
description: The GET /api/documents paginated metadata-only browse contract — filters spelled out as query parameters, mirroring DocumentFilter, so a filtered view is a plain shareable link.
resource: GET /api/documents
tags: [api, documents, rest, browse]
timestamp: 2026-08-16T00:00:00Z
---

# Documents Endpoint (`GET /api/documents`)

Browses decisions by metadata alone — no query text. Distinct from
[`/api/search`](/api/search.md): this is a plain paginated list, filterable and sortable
by date, with no ranking involved.

Filters are individual query parameters (`date_from`, `date_to`, `category`,
`decision_outcome`, `case_number`, `decision_number`, repeatable `entity_name`, repeatable
`entity_type`, repeatable `keyword`, `references_case_number`) rather than a nested JSON
body, so a filtered view is a link a user can share or bookmark. `keyword` matches
exactly, unlike `entity_name`'s substring match — see the [`keyword`
filter](/api/filters.md#keyword-filter). See [`/api/filters`](/api/filters.md) for the
values these accept.

## Other query parameters

| Parameter | Default | Notes |
|---|---|---|
| `newest_first` | `true` | Sorts by `decision_date`; nulls last, `document_id` tiebreak so a document cannot shift pages while a caller is paging through |
| `limit` | `search_default_limit` (10) | Clamped to `search_max_limit` (50) |
| `offset` | `0` | |

## Response

```json
{
  "items": [
    {
      "document_id": "uuid",
      "case_number": "string | null",
      "decision_number": "string | null",
      "decision_date": "date | null",
      "category": "string | null",
      "decision_outcome": "string | null",
      "headline": "string | null",
      "summary": "string | null",
      "source_url": "string",
      "source_published_at": "datetime | null",
      "has_pdf": true
    }
  ],
  "total": 0,
  "limit": 10,
  "offset": 0
}
```

`has_pdf` reflects whether the download worker recorded a stored URI
(`documents.gcs_uri is not None`), not a storage round trip.

Implemented by `api/services/document_service.list_documents` →
`shared.repositories.search.list_filtered_documents`/`count_filtered_documents`, served
through the [api package](/packages/api.md).

## No UI consumer

This endpoint is implemented, typed and reachable from the frontend —
`frontend/src/api/client.ts` exports `fetchDocuments`/`useDocuments` against it —
but no page calls either function. The [frontend](/frontend/overview.md) has no
document-browse page: [`/api/search`](/api/search.md) covers query-driven
discovery, and the vocabulary indexes (`/sokord`, `/begrepp`) cover
entity-driven traversal, so a plain metadata-filtered list has not had a route
built for it. Do not assume a page exists here without checking `frontend/src/`
directly — this contract has a client wrapper and no reader ever reaches it.
