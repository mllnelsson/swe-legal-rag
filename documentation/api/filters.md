---
type: API Endpoint
title: Filters Endpoint (GET /api/filters)
description: The GET /api/filters facet-vocabulary contract — the category, decision-outcome, entity-type and keyword values a search filter will actually match, plus the corpus's date range and size.
resource: GET /api/filters
tags: [api, search, rest, facets]
timestamp: 2026-08-03T00:00:00Z
---

# Filters Endpoint (`GET /api/filters`)

Reports the vocabulary [`/api/search`](/api/search.md) and
[`/api/documents`](/api/documents.md) filters will actually match. `category` and
`decision_outcome` are free text lifted off the PDFs by regex, not a controlled
vocabulary (see the [metadata worker](/pipeline/metadata.md)) — a client has no way to
guess valid values, so it has to be told. `keywords` is the exception and the strongest
of the four: it is the nämnd's own `Sökord` classification (see [document
structure](/reference/document-structure.md)), so its values are a real vocabulary rather
than whatever the regexes happened to lift.

## Response

```json
{
  "categories": [{"value": "string", "count": 0}],
  "decision_outcomes": [{"value": "string", "count": 0}],
  "entity_types": [{"value": "string", "count": 0}],
  "keywords": [{"value": "string", "count": 0}],
  "earliest_decision_date": "date | null",
  "latest_decision_date": "date | null",
  "document_count": 0
}
```

Each list is capped at `MAX_FACET_VALUES` (50), most-frequent value first — a browsable
vocabulary, not a dump. `entity_types` counts **documents** carrying at least one entity
of that type, not the number of entities, since "how many decisions can this narrow to"
is the question a filter vocabulary answers. `keywords` counts documents the same way,
scoped to [entities](/data-model/entities.md) of type `keyword`. Every facet is scoped to
the same population `find_candidate_documents`/`list_filtered_documents` search over — a
document with `raw_text` set — so a value reported here always matches at least one
document.

Implemented by `api/services/search_service.get_filters` →
`shared.repositories.search.get_facets`, served through the [api
package](/packages/api.md).

## `keyword` filter

[`/api/documents`](/api/documents.md) accepts a repeatable `keyword` query parameter and
[`POST /api/search`](/api/search.md) a `DocumentFilter.keywords` list, both narrowing to
documents carrying **any** of the given keyword entities. Matching is **exact** against
the lowercased value, unlike `entity_name`'s substring `ilike` — the values this endpoint
publishes are a controlled vocabulary a caller was handed, not a guess to search for, so
an exact match is the honest contract. It composes with `entity_name`/`entity_type`: they
are separate subqueries, so "this keyword *and* that regulation" is expressible.

This closes what was previously a known gap here: the trailer's `Sökord:` line was parsed
only to locate where the trailer starts, and its value was discarded — `category`, a
weaker free-text stand-in lifted from the header block, was the best facet on offer. It is
closed as [entities](/data-model/entities.md), not as a column on
[documents](/data-model/documents.md): a column can hold only one value, where a decision
can carry several keywords, and a column can be filtered but not traversed or browsed.
`shared.segmentation.parse_keywords` reads the value from the trailer the [extract
worker](/pipeline/extract.md) already segments; no migration was needed (see
[entities](/data-model/entities.md)).
