---
type: Concept
title: Query / Retrieval Agent
description: The five-step query agent — decompose, pre-filter, hybrid retrieve (RRF), optional rerank, synthesize — plus session context.
tags: [retrieval, agent, rrf, hybrid-search, synthesis]
timestamp: 2026-08-01T00:00:00Z
---

# Query / Retrieval Agent

The retrieval pipeline behind the [chat endpoint](/api/chat-endpoint.md), implemented in
the [api package](/packages/api.md) service layer.

## Step 1 — Query decomposition

A cheap LLM analyzes the user's Swedish question and extracts implicit date filters,
topic/category, decision type, entity references, and the core semantic question,
producing a structured query plan.

*Implementation:* `api/services/query_planner.py`. `plan_query()` calls
`ai.decompose_query()` → maps `DecomposeResult` onto `DocumentFilter`: `DateFilter.start/
end` → `date_from/date_to`; `categories[0]` → `category`; `entity_refs` →
`entity_names`; `include_appendices` passes through unchanged. Returns
`QueryPlan(semantic_query, filter, include_appendices)`. The mapping lives in `api` —
`shared` must not import from `ai`.

`include_appendices` is the planner's judgement that the question is about *det
överklagade beslutet* rather than Överklagandenämndens own ruling ("vad beslutade
stiftet?"). It is not a `DocumentFilter` field, because it selects parts of a document
rather than documents.

## Step 2 — Structured + entity pre-filter

Narrows the candidate set using metadata filters (SQL WHERE on date, category, outcome)
and entity-based filtering (join through [document_entities](/data-model/document-entities.md)),
and traverses [document_references](/data-model/document-references.md) when the query
implies precedent chains. The key trick: semantic search runs over ~50–100 filtered docs,
not the whole corpus.

*Implementation:* `search.find_candidate_documents(session, filter)` (a
[repository](/data-model/repositories.md) module function). Empty filter → the DB call is
skipped and `candidate_ids=None` (unfiltered) is used directly; a non-empty filter with
zero results also falls back to `None` (graceful degradation with a warning). Reference
traversal queries `document_references` in both directions.

## Step 3 — Hybrid retrieval

On the filtered subset, vector similarity search (pgvector) and full-text search (Swedish
tsvector) run in parallel, then scores combine with reciprocal rank fusion (RRF).

*Implementation:* `api/services/retriever.py`. `_hybrid_search()` runs
`asyncio.gather(vector_search, text_search)`, both capped at `RETRIEVAL_SEARCH_LIMIT`.
The question is embedded with the query prefix from `ai.get_embedding_prefixes()` —
`"query: "` under the default e5 model, and read from the same
[`llm_config.yaml`](/reference/llm-config.md) entry as the `"passage: "` prefix the
[embed worker](/pipeline/embed.md) applies at index time, so the two cannot drift
apart. (They did: the query side was prefixed while the passage side never was, which is
worse for retrieval than prefixing neither.) RRF fusion via
`shared.search.rrf.rrf_fuse(k=60)` then takes `[:RETRIEVAL_TOP_K]`. Document metadata is
hydrated concurrently.

### Section scoping

Both searches take a `sections` predicate on [`chunks.section`](/data-model/chunks.md).
`_sections_for(plan, settings)` resolves it:

| Condition | Sections searched |
|---|---|
| Default | `[body]` — Överklagandenämndens own text only |
| `RETRIEVAL_INCLUDE_APPENDICES=true` | all |
| `plan.include_appendices` (planner) | all |

If a body-only pass returns nothing, retrieval **retries unrestricted** and logs
`"No body chunks matched; widening search to appendices"` — mirroring the existing
empty-candidate fallback in step 2. The retry costs one extra round-trip, and only on
the empty path.

This is one HNSW index with a `WHERE` predicate, not two indexes, and a hard filter
rather than a ranking penalty — both choices are argued in
[body-first retrieval](/decisions/body-first-retrieval.md).

## Step 4 — Rerank (optional)

`_rerank()` in `retriever.py`, gated behind `RETRIEVAL_RERANK_ENABLED` (default `False`)
to satisfy [NFR1 (<5s)](/prd.md). Uses `llm_core.generate_structured()` with the
structured-role provider to return a ranked index list; any failure falls back to RRF
order — rerank never breaks retrieval.

## Step 5 — Synthesis

Feeds top chunks + metadata to the chat-role LLM (GLM 5.2 via Berget by default) to
generate a Swedish answer citing case numbers and dates.

*Implementation:* `api/services/answerer.py` streams tokens via `ai.synthesize_answer()`
→ yields a `TokenEvent` per token, then a single `SourcesEvent` (deduplicated, one
`SourceReference` per document, first-seen chunk in RRF order wins the excerpt, truncated
to 200 chars), then `DoneEvent`.

Each excerpt reaches the model tagged with its origin — `[Mål 1/2026]` for body text,
`[Mål 1/2026 - Bilaga A, det överklagade beslutet]` for an appendix — and the synthesis
prompt instructs the model never to present the latter as the nämnd's own position. The
same `section` and `appendix_label` travel on `SourceReference`, so the UI can label the
excerpt too. PDF URLs come from
`storage.get_url("documents/{doc_id}/original.pdf")`. The ordering `token* → sources →
done` is guaranteed.

## Session context

Conversation history lets the agent handle follow-ups like "what about after 2021?"
without re-explanation. Each `POST /api/chat` creates or loads a
[session](/data-model/sessions.md) by `session_id`; the `done` event returns it and
subsequent requests send it back. `history_for_llm()` truncates to the last
`SESSION_MAX_HISTORY_TURNS` turn-pairs before sending to the LLM. Stale or missing session
IDs silently create a new session. The `api` service layer owns session logic; the
`session` repo module owns DB access.
