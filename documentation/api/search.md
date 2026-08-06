---
type: API Endpoint
title: Search Endpoint (POST /api/search)
description: The POST /api/search hybrid search contract — free-text query plus explicit filters, document-grouped hits with full chunk text, per-arm ranks and similarity scores, and a diagnostics block that makes ranking auditable.
resource: POST /api/search
tags: [api, search, rest, hybrid-search, relevance]
timestamp: 2026-08-06T00:00:00Z
---

# Search Endpoint (`POST /api/search`)

Deterministic hybrid search over the decision corpus — no LLM in the path unless
`expand: true` is set. Separate from [chat](/api/chat-endpoint.md): every operation here
is a discrete request/response shaped as a tool an agent or MCP adapter can call
directly. The algorithm is described in [deterministic
search](/retrieval/deterministic-search.md); this concept is the wire contract.

POST rather than GET: `query` is free text of arbitrary length (up to 2000 characters)
and `filter` is a nested object with list-valued fields — awkward to encode in a query
string.

## Request

```json
{
  "query": "string (1-2000 chars)",
  "queries": ["optional caller-supplied phrasings"],
  "expand": false,
  "filter": {
    "date_from": "date | null",
    "date_to": "date | null",
    "category": "string | null",
    "decision_outcome": "string | null",
    "case_number": "string | null",
    "decision_number": "string | null",
    "entity_names": ["string"],
    "entity_types": ["string"],
    "references_case_number": "string | null"
  },
  "limit": "int | null",
  "offset": 0,
  "include_appendices": false,
  "chunks_per_document": "int | null"
}
```

`case_number`/`decision_number` are exact-identity filters — distinct from
`references_case_number`, which asks for documents that *cite or are cited by* the given
case. See [`/api/filters`](/api/filters.md) for the vocabulary these accept.

`queries`/`expand` are the [query expansion](/retrieval/query-expansion.md) surface: an
agent that has already reinterpreted the question passes `queries` directly; `expand:
true` asks the server to produce them instead.

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
      "score": 0.0,
      "matched_chunk_count": 1,
      "chunks": [
        {
          "chunk_id": "uuid",
          "chunk_index": 0,
          "text": "string",
          "section": "body | appendix",
          "appendix_label": "string | null",
          "score": 0.0,
          "vector_rank": "int | null",
          "text_rank": "int | null",
          "vector_similarity": "float | null",
          "text_score": "float | null"
        }
      ]
    }
  ],
  "total": 0,
  "limit": 10,
  "offset": 0,
  "effective_queries": ["string"],
  "diagnostics": {
    "filter_applied": false,
    "candidate_document_count": null,
    "vector_hit_count": 0,
    "text_hit_counts": {"query text": 0},
    "fused_chunk_count": 0,
    "expanded": false,
    "widened_to_appendices": false,
    "vector_similarity_floor": 0.78,
    "top_vector_similarity": null
  }
}
```

Results are grouped by document — one entry per matching decision — carrying full chunk
text (never a truncated excerpt) up to `chunks_per_document` (default 3), ordered by
fused score. `vector_rank`/`text_rank` of `null` means that arm did not return the chunk
at all, so ranking quality can be checked by eye rather than trusted blindly.

`total` is the size of the fused candidate pool (bounded by `search_arm_limit`, default
50 per arm), **not a corpus-wide count.** Paging is shallow by design — see
[deterministic search](/retrieval/deterministic-search.md).

## Reading relevance: `score` is not a rating

`score`, on both `SearchHit` and `SearchChunk`, is the Reciprocal Rank Fusion value. It
orders the result; it does not grade it. RRF derives it from rank alone, so **the top hit
of any search scores `1/(60+1)` = 0.01639** — a decision that answers the question and
the nearest paragraph to a question the corpus never addresses are indistinguishable by
this number. Do not render it as a percentage, a rating, or a confidence.

Relevance lives in two other fields:

| Field | What it is | Comparable across queries? |
|---|---|---|
| `vector_similarity` | Cosine similarity to the query embedding, always at or above `diagnostics.vector_similarity_floor` | **Yes.** This is the field to threshold on or display |
| `text_score` | Postgres `ts_rank` over the Swedish tsvector | No — `ts_rank` has no absolute scale |

Both are `null` when that arm did not return the chunk, exactly like
`vector_rank`/`text_rank`. A hit whose `vector_similarity` is `null` matched on words
alone; a hit whose `text_score` is `null` matched on meaning alone.

## Empty results: three distinct nothings

The vector arm applies a similarity floor, so a query the corpus has nothing close to
returns **no results** rather than its nearest neighbours. `diagnostics` tells the three
cases apart:

| Case | Signature |
|---|---|
| The filter excluded every decision | `candidate_document_count: 0` |
| Nothing was close enough to the query | `filter_applied: false`, `vector_hit_count: 0`, `top_vector_similarity: null` |
| Results, but matched by meaning only | `items` non-empty, every `text_hit_counts` value `0` |

See [the similarity floor](/retrieval/deterministic-search.md#the-similarity-floor) for
how the default was calibrated and why it is model-specific.

## Filter semantics: no fallback

A `filter` that matches no documents returns an **empty result**, not a wider unfiltered
search — `diagnostics.candidate_document_count: 0` explains why. This is the opposite of
the [chat retriever](/retrieval/agent.md), which falls back to an unfiltered search when
its filter yields nothing, and it is deliberate: chat prefers an answer from a wider net
over no answer, but a search tool that silently ignored "nothing older than 2024" and
answered with 2019 decisions would be lying to its caller.

## Appendix scoping

Body-only by default (`include_appendices: false`); every chunk's `section` and
`appendix_label` say which text it is regardless of scope. If a body-only search finds
nothing, it widens once to the whole document and sets
`diagnostics.widened_to_appendices: true`. The widened pass applies the same similarity
floor, so it can also return nothing — `widened_to_appendices: true` means the retry
happened, not that it produced results. See [body-first
retrieval](/decisions/body-first-retrieval.md).

## Query expansion

`expand: true` calls `ai.expand_query` for up to `search_max_query_variants` alternate
phrasings, fused into the same RRF pool as the original query — expansion only adds
rankings, it never replaces the question. `effective_queries` echoes exactly what was
searched, so passing it back as `queries` with `expand: false` replays the same result.
See [query expansion](/retrieval/query-expansion.md).

## Settings

`SearchSettings` (`api/config.py`): `search_default_limit` (10), `search_max_limit`
(50), `search_arm_limit` (50, per arm per query), `search_chunks_per_document` (3),
`search_candidate_limit` (500), `search_max_query_variants` (3),
`search_expand_vector_arm` (`false`), `search_min_vector_similarity` (0.78).

Implemented by `api/services/search_service.py`, served through the [api
package](/packages/api.md).
