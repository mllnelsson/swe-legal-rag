# API

## Chat

* [Chat Endpoint (POST /api/chat)](chat-endpoint.md) - The POST /api/chat Server-Sent Events contract — a Swedish question in, progress keys then a streamed answer out; the closed label vocabulary a client maps its own words onto, the mandatory sql event, the terminal error semantics, and the X-Interaction-Id correlation header.

## Search

* [Search Endpoint (POST /api/search)](search.md) - The POST /api/search hybrid search contract — free-text query plus explicit filters, document-grouped hits with full chunk text, per-arm ranks and similarity scores, and a diagnostics block that makes ranking auditable.
* [Filters Endpoint (GET /api/filters)](filters.md) - The GET /api/filters facet-vocabulary contract — the category, decision-outcome and entity-type values a search filter will actually match, plus the corpus's date range and size.

## Documents

* [Documents Endpoint (GET /api/documents)](documents.md) - The GET /api/documents paginated metadata-only browse contract — filters spelled out as query parameters, mirroring DocumentFilter, so a filtered view is a plain shareable link.
* [Document Detail Endpoint (GET /api/documents/{id})](document-detail.md) - The GET /api/documents/{id} contract — one decision's identity, section counts, legal concepts/regulations/roles/parishes, and both directions of its citation graph, in one call.
* [Document Chunks Endpoint (GET /api/documents/{id}/chunks)](document-chunks.md) - The GET /api/documents/{id}/chunks contract — a decision's full text in reading order, chunk by chunk, optionally scoped to one section.
* [Document PDF Endpoint (GET /api/documents/{id}/pdf)](document-pdf.md) - The GET /api/documents/{id}/pdf contract — the original PDF streamed inline as application/pdf, proxied through the API rather than a signed storage URL.

## Concepts (entities)

* [Concepts Endpoint (GET /api/concepts)](concepts.md) - The GET /api/concepts contract — browsing the knowledge graph's nodes (legal concepts, regulations, roles, parishes) with the document count each carries, optionally filtered by type or name.
* [Concept Documents Endpoint (GET /api/concepts/{id}/documents)](concept-documents.md) - The GET /api/concepts/{id}/documents contract — every decision carrying a given entity, the reverse traversal hop from a concept back to the decisions that name it.

## Keywords (entities)

* [Keywords Endpoint (GET /api/keywords)](keywords.md) - The GET /api/keywords contract — browsing the nämnd's own Sökord subject classification, most-used first, with the document count each keyword carries.
* [Keyword Documents Endpoint (GET /api/keywords/{id}/documents)](keyword-documents.md) - The GET /api/keywords/{id}/documents contract — every decision classified under a given Sökord keyword, the reverse traversal hop from a keyword back to the decisions that declare it.

## SQL agent

* [SQL Agent Endpoint (POST /api/sql)](sql-agent.md) - The POST /api/sql text-to-SQL contract — a Swedish question in, the generated read-only query and its rows out, never an interpreted answer — plus the caller's obligation to surface the query, the never-500s refusal semantics, and the X-Interaction-Id correlation header.
