---
type: Concept
title: Deterministic Search
description: The LLM-free hybrid search path behind POST /api/search — filter narrowing with no fallback, parallel vector/text arms fused by RRF, appendix widening, and document-level ranking that never fetches metadata for documents it will not return.
tags: [retrieval, search, rrf, hybrid-search, rest]
timestamp: 2026-08-03T00:00:00Z
---

# Deterministic Search

The retrieval path behind [`POST /api/search`](/api/search.md), implemented in
`api/services/search_service.py`. It sits alongside the [query/retrieval
agent](/retrieval/agent.md) rather than replacing it: chat needs a synthesized answer
from a wide net, search needs an auditable, repeatable result set. No LLM sits in this
path by default — the one unavoidable model call is the query embedding; [query
expansion](/retrieval/query-expansion.md) is opt-in and, when used, only adds rankings
to the same fusion. Given the same inputs, this returns the same results, which is what
lets it double as a tool an agent or MCP adapter calls directly.

Ten deterministic REST endpoints make up this tool set: [search](/api/search.md),
[filters](/api/filters.md), [documents](/api/documents.md), [document
detail](/api/document-detail.md), [chunks](/api/document-chunks.md),
[pdf](/api/document-pdf.md), [concepts](/api/concepts.md), [concept
documents](/api/concept-documents.md), [keywords](/api/keywords.md) and [keyword
documents](/api/keyword-documents.md).

**Why REST, not the agent's own transport.** Every operation here is a discrete
request/response with no server push — a filter facet lookup, a search, a PDF fetch are
each one round trip, and MCP's own transports are stdio and streamable-HTTP, so REST is
also the shortest path to exposing this as a tool set later. The portability guarantee is
architectural rather than a transport detail: every service function in
`api/services/search_service.py`, `document_service.py`, `concept_service.py` and
`keyword_service.py` takes `(AsyncSession, a typed pydantic model)` and returns typed
pydantic models — never a FastAPI `Request`/`Response`. `keyword_service.py` follows the
same discipline as the rest, which is what lets a future MCP tool wrapper cover the
keyword endpoints for free, with no special-casing. Routes in `api/routes/` are thin
adapters over them, so the same call works from a test, a route, or a future MCP tool
wrapper.

## Steps

1. **Resolve queries.** `query` is always searched. `queries` (caller-supplied
   phrasings) are deduplicated and appended; `expand: true` instead calls
   `ai.expand_query()` to produce them. See [query expansion](/retrieval/query-expansion.md).
2. **Filter narrowing, no fallback.** A non-empty `filter` calls
   `search_repo.find_candidate_documents(limit=search_candidate_limit)`. If it returns
   zero candidates, the search stops immediately with an empty result and
   `diagnostics.candidate_document_count: 0` — **no widening to an unfiltered
   search.** This is the deliberate opposite of the [chat
   retriever](/retrieval/agent.md), which falls back to an unfiltered search when its
   filter yields nothing: an answer from a wider net beats no answer for chat, but a
   search tool asked for "nothing older than 2024" must not silently answer with 2019
   decisions.
3. **Embed queries.** The query-side prefix from `ai.get_embedding_prefixes()` is
   applied. Only the original query is embedded for the vector arm unless
   `search_expand_vector_arm` is `true` (default `false`) — see [query
   expansion](/retrieval/query-expansion.md) for why.
4. **Hybrid arms, in parallel.** `chunk_repo.vector_search` and `chunk_repo.text_search`
   run via `asyncio.gather` for every query, each capped at `search_arm_limit`. Body-only
   `sections` scoping applies by default, same mechanism as [body-first
   retrieval](/decisions/body-first-retrieval.md).
5. **Appendix widening.** If body-only arms return no chunks at all, the arms rerun once
   with no section restriction and `diagnostics.widened_to_appendices` is set — mirroring
   the agent's own widen-on-empty behavior, and for the same reason: every chunk still
   carries its own `section`/`appendix_label`, so a caller can tell whose words a widened
   hit is quoting.
6. **Fusion.** All rankings — every query's vector ranking and every query's text
   ranking — fuse through `shared.search.rrf_fuse_scored(rankings, k=DEFAULT_RRF_K)`
   (`k=60`). The function takes arbitrarily many rankings, which is what lets query
   expansion add rankings without a special case.
7. **Group by document, then rank documents.** Fused chunks bucket by `document_id`.
   Documents rank by `(-best chunk score, -matched chunk count, document_id)` —
   `document_id` is the final tiebreak, deliberately **not** `decision_date`, because
   fetching document metadata to break a tie would mean hydrating documents that might
   not make the page.
8. **Page, then hydrate.** `total` is `len(ranked_document_ids)` — **the size of the
   fused pool, bounded by `search_arm_limit` per arm, not a corpus-wide count.** Paging
   is shallow by design. Document metadata (`document_repo.get_by_id`) is fetched only
   for the page being returned.

## Diagnostics

`SearchDiagnostics`, returned alongside every response, is what makes the above
auditable rather than opaque:

| Field | Meaning |
|---|---|
| `filter_applied` | Whether a non-empty `filter` was used |
| `candidate_document_count` | `null` if no filter; `0` explains an empty result |
| `vector_hit_count` | Distinct chunks the vector arm(s) returned |
| `text_hit_counts` | Hits per query string on the text arm |
| `fused_chunk_count` | Chunks entering the RRF fusion |
| `expanded` | Whether any variant beyond `query` was searched |
| `widened_to_appendices` | Whether step 5 fired |

## Why results are document-grouped with full chunk text

Each `SearchHit` carries every matched chunk verbatim — not a truncated excerpt — plus
per-chunk `vector_rank`/`text_rank` (`null` when that arm never returned the chunk at
all). This is so ranking quality can be checked by eye against the fused score, which a
truncated excerpt or a single best-chunk view would hide.

## Settings

`SearchSettings` (`api/config.py`), separate from `RetrievalSettings` so the two paths
tune independently:

| Setting | Default | Meaning |
|---|---|---|
| `search_default_limit` | 10 | Page size when `limit` is omitted |
| `search_max_limit` | 50 | Ceiling `limit` clamps to |
| `search_arm_limit` | 50 | Per-arm, per-query cap; total chunks entering fusion is bounded by this × (1 vector arm + N text arms) |
| `search_chunks_per_document` | 3 | Chunks returned per hit when `chunks_per_document` is omitted |
| `search_candidate_limit` | 500 | Ceiling on how many documents a filter may narrow to before becoming an `IN` list |
| `search_max_query_variants` | 3 | Cap on expansion variants |
| `search_expand_vector_arm` | `false` | Whether expansion variants also drive the vector arm |

Served through the [api package](/packages/api.md); the wire contract is
[`POST /api/search`](/api/search.md).
