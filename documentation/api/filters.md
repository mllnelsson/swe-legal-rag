---
type: API Endpoint
title: Filters Endpoint (GET /api/filters)
description: The GET /api/filters facet-vocabulary contract — the category, decision-outcome and entity-type values a search filter will actually match, plus the corpus's date range and size.
resource: GET /api/filters
tags: [api, search, rest, facets]
timestamp: 2026-08-03T00:00:00Z
---

# Filters Endpoint (`GET /api/filters`)

Reports the vocabulary [`/api/search`](/api/search.md) and
[`/api/documents`](/api/documents.md) filters will actually match. `category` and
`decision_outcome` are free text lifted off the PDFs by regex, not a controlled
vocabulary (see the [metadata worker](/pipeline/metadata.md)) — a client has no way to
guess valid values, so it has to be told.

## Response

```json
{
  "categories": [{"value": "string", "count": 0}],
  "decision_outcomes": [{"value": "string", "count": 0}],
  "entity_types": [{"value": "string", "count": 0}],
  "earliest_decision_date": "date | null",
  "latest_decision_date": "date | null",
  "document_count": 0
}
```

Each list is capped at `MAX_FACET_VALUES` (50), most-frequent value first — a browsable
vocabulary, not a dump. `entity_types` counts **documents** carrying at least one entity
of that type, not the number of entities, since "how many decisions can this narrow to"
is the question a filter vocabulary answers. Every facet is scoped to the same population
`find_candidate_documents`/`list_filtered_documents` search over — a document with
`raw_text` set — so a value reported here always matches at least one document.

Implemented by `api/services/search_service.get_filters` →
`shared.repositories.search.get_facets`, served through the [api
package](/packages/api.md).

## Known gap: `Sökord` is not a facet

The decisions carry their own keywords on the trailer's `Sökord:` line — the
nämnd's own subject classification, and by some distance the best facet this
endpoint could offer. It is not here.

`worker-metadata` already *parses* the trailer (see [decision document
structure](/reference/document-structure.md)), but `Sökord` is discarded: no
column holds it, so nothing can group by it. `category` — a free-text line lifted
from the header block — is the weaker stand-in currently reported.

Closing the gap is pipeline work, not API work: a column on
[documents](/data-model/documents.md), a migration, an extractor in
[worker-metadata](/pipeline/metadata.md), and a re-parse of the corpus. All of
that is cheap while [nothing is
ingested](/reference/deployment-state.md) and was deliberately left out of the
retrieval API's scope rather than deferred for cost.
