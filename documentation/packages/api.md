---
type: Package
title: api Package
description: The FastAPI application, the chat retrieval service layer, and the deterministic search/browse/traversal REST API — query planner, retriever, answerer, session service, search/document/concept services, and their routes.
resource: packages/api
tags: [package, api, fastapi, retrieval, sse, search, rest]
timestamp: 2026-08-03T00:00:00Z
---

# api Package (`packages/api/`)

Hosts the FastAPI application, the chat retrieval-pipeline service layer, and the
deterministic search/browse/traversal REST API. Depends on `shared` (repositories, DTOs,
storage) and [ai](/packages/ai.md) (decompose, synthesize, embed, expand); it also
declares `llm-core` directly in `pyproject.toml`, since `retriever.py` imports it for its
rerank call rather than reaching it transitively through `ai`. The end-to-end chat
retrieval flow is described in the [retrieval agent](/retrieval/agent.md), and the
deterministic search algorithm in [deterministic search](/retrieval/deterministic-search.md);
this concept covers the package's structure and the HTTP layer for both.

## Config (`api/config.py`)

`RetrievalSettings` — `RETRIEVAL_TOP_K` (8), `RETRIEVAL_SEARCH_LIMIT` (20),
`RETRIEVAL_RERANK_ENABLED` (False — default off for [NFR1 <5s](/prd.md)).
`SessionSettings` — `SESSION_MAX_HISTORY_TURNS` (10). `AppSettings` — `API_CORS_ORIGINS`
(`["http://localhost:5173"]`, the Vite dev default). `SearchSettings` — bounds for the
search API, deliberately separate from `RetrievalSettings` so the two paths tune without
disturbing each other; see [deterministic search](/retrieval/deterministic-search.md#settings)
for the full table of defaults. Each exposes an `@lru_cache` singleton getter.

## Shared HTTP infrastructure

- **`api/dependencies.py`** — `get_db()`, a FastAPI dependency yielding an
  `AsyncSession` via `shared.db.get_async_session()`. Lifted out of `routes/chat.py` so
  every router (chat, search, documents, concepts) shares one session seam and one
  `app.dependency_overrides` target for tests, rather than each route module declaring
  its own.
- **`api/pagination.py`** — the generic `Page[T]` model (`items`, `total`, `limit`,
  `offset`) every list-returning endpoint uses, and `clamp_limit(requested, *, default,
  maximum)`, which keeps a caller-supplied page size inside what the server will serve.

## Chat service layer (`api/services/`) — the deprecated agent surface

`POST /api/chat` and the four services behind it are the package's LLM-driven,
stateful, streaming half — the agent, not the deterministic tool set the rest of this
package is. Each carries a `# DEPRECATED —` marker comment and the route is decorated
`deprecated=True`, per [the chat endpoint](/api/chat-endpoint.md). Nothing here
changed behaviourally; the marker is an ownership signal that this surface is slated
to move to a future `agent` package.

**The extraction set is clean:** no retrieval endpoint or service imports any of the
four chat services, and `routes/chat.py` is their only importer, so the chat surface
can be lifted out wholesale. What moves with it: the four services below, the
`RetrievalSettings` and `SessionSettings` classes in `api/config.py`,
`ai.decompose_query` and `ai.synthesize` in the [ai package](/packages/ai.md), and the
[`sessions`](/data-model/sessions.md) table. `ai.expand_query` does **not** move —
query expansion belongs to search; see [query expansion](/retrieval/query-expansion.md).

- **`query_planner.py`** — `plan_query(question, history, *, llm_provider=None) ->
  QueryPlan`. Calls `ai.decompose_query()` and maps `DecomposeResult` onto
  `DocumentFilter` (`DateFilter.start/end` → `date_from/date_to`; `categories[0]` →
  `category`; `entity_refs` → `entity_names`). The `ai`→`shared` mapping lives here only.
- **`retriever.py`** — `retrieve(plan, session, *, embedding_provider, settings) ->
  list[RetrievedChunk]`. Pre-filter (via `shared.search.is_empty_filter`) → embed
  (`"query: "` prefix) → hybrid search (`asyncio.gather(vector, text)`) → RRF fusion →
  optional `_rerank()` → metadata hydration. The e5 `"query: "`/`"passage: "` prefixes
  are symmetric and must stay consistent with the [embed worker](/pipeline/embed.md).
- **`answerer.py`** — typed SSE events `TokenEvent`/`SourcesEvent`/`DoneEvent`
  (`AnswerEvent` union). `answer_query(...)` calls `plan_query()` → `retrieve()` →
  `ai.synthesize_answer()`, yields token events (also accumulated for persistence, never
  buffering the stream), a deduplicated `SourcesEvent` (one `SourceReference` per
  document, first-seen chunk wins, `excerpt` first 200 chars, `pdf_url` from
  `storage.get_url(shared.storage.keys.document_pdf_key(document_id))`), then
  `DoneEvent`; persists the turn via `session_service.append_turn()` afterwards.
- **`session_service.py`** — module-level functions:
  `get_or_create_session(session_id, session)` (None or stale id → fresh session, no
  error), `append_turn(...)` (appends user + assistant entries, updates `last_active_at`,
  no-op on missing id), `history_for_llm(session, max_turns)` (returns the last
  `max_turns * 2` entries, preserving complete pairs; full history stays in the DB).

## Search/browse/traversal service layer (`api/services/`)

Every function here takes `(AsyncSession, a typed pydantic model)` and returns typed
pydantic models — never a FastAPI `Request`/`Response` — so the same call works from a
route, a test, or a future MCP tool wrapper. See [deterministic
search](/retrieval/deterministic-search.md) for why.

- **`search_service.py`** — `search_documents(query: SearchQuery, session, *,
  embedding_provider, settings, llm_provider=None) -> SearchResponse` and
  `get_filters(session) -> DocumentFacets`. Implements
  [`POST /api/search`](/api/search.md) and [`GET /api/filters`](/api/filters.md).
- **`document_service.py`** — `list_documents`, `get_document_detail`,
  `get_document_chunks`, `get_document_pdf`. Implements
  [`GET /api/documents`](/api/documents.md),
  [`GET /api/documents/{id}`](/api/document-detail.md),
  [`GET /api/documents/{id}/chunks`](/api/document-chunks.md) and
  [`GET /api/documents/{id}/pdf`](/api/document-pdf.md).
- **`concept_service.py`** — `list_concepts`, `list_documents_for_concept`. Implements
  [`GET /api/concepts`](/api/concepts.md) and
  [`GET /api/concepts/{id}/documents`](/api/concept-documents.md).

## FastAPI app (`api/main.py`)

`create_app() -> FastAPI`. The lifespan handler sets `app.state.embedding_provider` and
`app.state.storage` at startup (and runs `ai.verify_embedding_dimension` — see
[embedding dimension](/decisions/embedding-dimension.md)); CORS is configured from
`AppSettings.api_cors_origins`. Routes: the search, documents and concepts routers are
registered ahead of the chat router, plus `GET /healthz`.

## Chat route (`api/routes/chat.py`) — deprecated

Implements the [chat endpoint](/api/chat-endpoint.md) contract; `@router.post("/api/chat",
deprecated=True)` marks it as such in the OpenAPI schema and Swagger UI.

| Symbol | Kind | Purpose |
|---|---|---|
| `ChatRequest` | Pydantic model | `session_id: UUID \| None`, `message: str` (1–4000 chars) |
| `_format_sse(event, data)` | pure function | Produces an `event: …\ndata: …\n\n` frame |
| `chat_endpoint` | route handler | Orchestrates session + `answer_query()` + SSE streaming; dispatches events via `match`/`case` over `AnswerEvent` |

Request flow: validate `ChatRequest` (422 on empty/long/bad `session_id`) →
`get_or_create_session` → `history_for_llm` → `answer_query` (async generator) →
`_format_sse` each event → `StreamingResponse` (`text/event-stream`, headers
`Cache-Control: no-cache`, `X-Accel-Buffering: no`); the `done` frame carries the
`session_id`. The DB session comes from `api/dependencies.get_db`, shared with every
other router.

## Search, document and concept routes (`api/routes/`)

`search.py`, `documents.py` and `concepts.py` are thin adapters: each route validates
input, calls one service function, and either returns its pydantic model directly or
raises `HTTPException`. Full wire contracts are documented per endpoint under
[API](/api/index.md).

## API server design decisions

- **Error event instead of mid-stream HTTP error (chat only):** once a
  `StreamingResponse` starts, headers are sent, so a synthesis failure emits `event:
  error` (generic safe message) and stops; `done` is absent and the failed turn is not
  persisted. The search/documents/concepts routes are plain request/response, so they use
  ordinary HTTP status codes throughout.
- **No `errors.py` in this package.** Search/document/concept services return `None` for
  a missing row; routes raise `HTTPException(404)` at the boundary. Nothing here throws a
  domain error worth its own hierarchy.
- **Token accumulation without SSE buffering:** tokens stream as they arrive and are also
  collected locally so the full answer can be persisted after `DoneEvent` — accumulation
  never delays the stream.
- **Stale session IDs create fresh sessions:** unrecognized ids degrade gracefully.
- **Full history in DB, truncated window to LLM:** all turns append to
  [sessions.history](/data-model/sessions.md); only the last `max_turns * 2` entries go to
  the LLM.
- **One DB dependency for every router:** `api/dependencies.get_db` is the single
  `app.dependency_overrides` target tests replace, rather than each router declaring its
  own.
- **Repository Protocols were not extended for these services.** `repositories/_protocols.py`
  declares only the structural interfaces *workers* call (interface segregation); the new
  search/document/concept repository functions are imported as plain modules here, the
  same way non-worker call sites already did.
