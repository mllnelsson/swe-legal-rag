---
type: Package
title: api Package
description: The FastAPI application and retrieval service layer — query planner, retriever, answerer, session service, and the chat route.
resource: packages/api
tags: [package, api, fastapi, retrieval, sse]
timestamp: 2026-07-24T00:00:00Z
---

# api Package (`packages/api/`)

Hosts the FastAPI application and the retrieval-pipeline service layer. Depends on
`shared` (repositories, DTOs, storage) and [ai](/packages/ai.md) (decompose, synthesize,
embedding). The end-to-end retrieval flow is described in the
[retrieval agent](/retrieval/agent.md); this concept covers the package's structure and
the HTTP layer.

## Config (`api/config.py`)

`RetrievalSettings` — `RETRIEVAL_TOP_K` (8), `RETRIEVAL_SEARCH_LIMIT` (20),
`RETRIEVAL_RERANK_ENABLED` (False — default off for [NFR1 <5s](/prd.md)).
`SessionSettings` — `SESSION_MAX_HISTORY_TURNS` (10). `AppSettings` — `API_CORS_ORIGINS`
(`["http://localhost:5173"]`, the Vite dev default). Each exposes an `@lru_cache`
singleton getter.

## Service layer (`api/services/`)

- **`query_planner.py`** — `plan_query(question, history, *, llm_provider=None) ->
  QueryPlan`. Calls `ai.decompose_query()` and maps `DecomposeResult` onto
  `DocumentFilter` (`DateFilter.start/end` → `date_from/date_to`; `categories[0]` →
  `category`; `entity_refs` → `entity_names`). The `ai`→`shared` mapping lives here only.
- **`retriever.py`** — `retrieve(plan, session, *, embedding_provider, settings) ->
  list[RetrievedChunk]`. Pre-filter → embed (`"query: "` prefix) → hybrid search
  (`asyncio.gather(vector, text)`) → RRF fusion → optional `_rerank()` → metadata
  hydration. The e5 `"query: "`/`"passage: "` prefixes are symmetric and must stay
  consistent with the [embed worker](/pipeline/embed.md).
- **`answerer.py`** — typed SSE events `TokenEvent`/`SourcesEvent`/`DoneEvent`
  (`AnswerEvent` union). `answer_query(...)` calls `plan_query()` → `retrieve()` →
  `ai.synthesize_answer()`, yields token events (also accumulated for persistence, never
  buffering the stream), a deduplicated `SourcesEvent` (one `SourceReference` per
  document, first-seen chunk wins, `excerpt` first 200 chars, `pdf_url` from
  `storage.get_url(...)`), then `DoneEvent`; persists the turn via
  `session_service.append_turn()` afterwards.
- **`session_service.py`** — module-level functions:
  `get_or_create_session(session_id, session)` (None or stale id → fresh session, no
  error), `append_turn(...)` (appends user + assistant entries, updates `last_active_at`,
  no-op on missing id), `history_for_llm(session, max_turns)` (returns the last
  `max_turns * 2` entries, preserving complete pairs; full history stays in the DB).

## FastAPI app (`api/main.py`)

`create_app() -> FastAPI`. The lifespan handler sets `app.state.embedding_provider` and
`app.state.storage` at startup (and runs `ai.verify_embedding_dimension` — see
[embedding dimension](/decisions/embedding-dimension.md)); CORS is configured from
`AppSettings.api_cors_origins`. Routes: `POST /api/chat` and `GET /healthz`.

## Chat route (`api/routes/chat.py`)

Implements the [chat endpoint](/api/chat-endpoint.md) contract.

| Symbol | Kind | Purpose |
|---|---|---|
| `ChatRequest` | Pydantic model | `session_id: UUID \| None`, `message: str` (1–4000 chars) |
| `_format_sse(event, data)` | pure function | Produces an `event: …\ndata: …\n\n` frame |
| `_get_db()` | FastAPI dependency | Yields `AsyncSession`; overridable in tests via `app.dependency_overrides` |
| `chat_endpoint` | route handler | Orchestrates session + `answer_query()` + SSE streaming; dispatches events via `match`/`case` over `AnswerEvent` |

Request flow: validate `ChatRequest` (422 on empty/long/bad `session_id`) →
`get_or_create_session` → `history_for_llm` → `answer_query` (async generator) →
`_format_sse` each event → `StreamingResponse` (`text/event-stream`, headers
`Cache-Control: no-cache`, `X-Accel-Buffering: no`); the `done` frame carries the
`session_id`.

## API server design decisions

- **Error event instead of mid-stream HTTP error:** once a `StreamingResponse` starts,
  headers are sent, so a synthesis failure emits `event: error` (generic safe message)
  and stops; `done` is absent and the failed turn is not persisted.
- **Token accumulation without SSE buffering:** tokens stream as they arrive and are also
  collected locally so the full answer can be persisted after `DoneEvent` — accumulation
  never delays the stream.
- **Stale session IDs create fresh sessions:** unrecognized ids degrade gracefully.
- **Full history in DB, truncated window to LLM:** all turns append to
  [sessions.history](/data-model/sessions.md); only the last `max_turns * 2` entries go to
  the LLM.
- **DB dependency is injectable:** `_get_db` is replaced in tests via
  `app.dependency_overrides`.
