---
type: Package
title: api Package
description: The FastAPI application and the deterministic search/browse/traversal REST API — search/document/concept/keyword services, the session service, the chat toolset the conversational agent is driven through, and their routes.
resource: packages/api
tags: [package, api, fastapi, retrieval, sse, search, rest]
timestamp: 2026-08-25T00:00:00Z
---

# api Package (`packages/api/`)

Hosts the FastAPI application and the deterministic search/browse/traversal REST API.
Depends on `shared` (repositories, DTOs, storage), [ai](/packages/ai.md) (synthesize,
embed, expand), [agents](/packages/agents.md) (both agents) and `llm-core` (provider
types, declared directly rather than reached transitively through `ai`).

The retrieval algorithm is described in [deterministic
search](/retrieval/deterministic-search.md) and the agent that drives it in [the
conversational agent](/retrieval/chat-agent.md); this concept covers the package's
structure and its HTTP layer.

**No agent loop lives here.** Both agents are in `agents`; this package supplies the
tools one of them runs on and the SSE framing both reach a client through.

## Config (`api/config.py`)

`SessionSettings` — `SESSION_MAX_HISTORY_TURNS` (10). `AppSettings` —
`API_CORS_ORIGINS` (`["http://localhost:5173"]`, the Vite dev default).
`SearchSettings` — bounds for the search API, and therefore also the bounds the
[conversational agent](/retrieval/chat-agent.md) searches under, since its search tool
wraps the same path; see [deterministic
search](/retrieval/deterministic-search.md#settings) for the full table of defaults.
`DevSettings` — `CHAT_SCRIPT` (`off`), typed as the `ChatScript` enum so a
misspelt value fails at startup rather than falling through to the real agent.
Each exposes an `@lru_cache` singleton getter.

The agent's own bounds — iterations, reading budget, citation cap — are
`ChatAgentSettings` in [agents](/packages/agents.md), next to the loop they govern.

## Shared HTTP infrastructure

- **`api/dependencies.py`** — `get_db()`, a FastAPI dependency yielding an
  `AsyncSession` via `shared.db.get_async_session()`. Lifted out of `routes/chat.py` so
  every router (chat, search, documents, concepts) shares one session seam and one
  `app.dependency_overrides` target for tests, rather than each route module declaring
  its own.
- **`api/pagination.py`** — the generic `Page[T]` model (`items`, `total`, `limit`,
  `offset`) every list-returning endpoint uses, and `clamp_limit(requested, *, default,
  maximum)`, which keeps a caller-supplied page size inside what the server will serve.
- **`api/correlation.py`** — `INTERACTION_ID_HEADER` (`X-Interaction-Id`) and
  `resolve_interaction_id(supplied)`, shared by the chat and SQL routes. The header is
  honoured only when it parses as a UUID and is canonicalised when it does; anything
  else is ignored and an id minted. It lives here rather than in either route because
  `api/main.py` also needs the header name — see [the CORS
  requirement](#fastapi-app-apimainpy). See [LLM Observability](/observability.md) for
  what the id correlates. `interaction_id_of(request)` reads the id
  `AccessLogMiddleware` already resolved off `request.scope["state"]`, falling back to
  resolving it fresh only for a request built without that middleware — a route asking
  `resolve_interaction_id` directly would mint a second id for the same turn.
- **`api/access_log.py`** / **`api/logging_setup.py`** — the API's per-request log line
  and the process-wide logging setup (`configure_api_logging()`, uvicorn adoption, the
  interaction-id log filter, `preview()`'s 120-character truncation). Covered in full in
  [Application Logging](/logging.md), which is where this behaviour belongs — it applies
  to every process in the repo, not just this package.

## The chat surface (`api/services/`)

Two modules, and neither is an agent — the loop lives in
[agents](/packages/agents.md).

- **`chat_toolset.py`** — `ApiChatToolset` / `build_chat_toolset(session, *,
  embedding_provider, search_settings, sql_llm_provider)`. Satisfies the `ChatToolset`
  Protocol by mapping the agent's five capabilities onto `search_service`,
  `document_service`, `keyword_service`, `concept_service` and `agents.run_sql_agent`,
  and converting their results into the agent's own shapes. This is the only place the
  two halves meet, and it sits on the `api` side of the edge so the dependency stays
  `api → agents`. A class rather than a module of functions because the Protocol wants
  an object carrying its per-request dependencies.

  Two fields it takes care to carry: `vector_similarity` on every chunk and the search
  diagnostics, because the fused `score` is rank-derived and cannot tell the agent
  whether the corpus actually addresses a question — see [the similarity
  floor](/retrieval/deterministic-search.md#the-similarity-floor).
- **`session_service.py`** — module-level functions:
  `get_or_create_session(session_id, session)` (None or stale id → fresh session, no
  error), `append_turn(..., interaction_id)` (appends user + assistant entries, both
  tagged with the interaction, updates `last_active_at`, no-op on missing id),
  `history_for_llm(session, max_turns)` (returns the last `max_turns * 2` entries,
  preserving complete pairs; full history stays in the DB).
  Only the question and the answer are persisted — never the evidence a turn gathered,
  which would otherwise be re-sent on the next turn.

  `append_turn` no longer reads the session before writing it — it calls
  `session_repo.append_history`, one `UPDATE ... history || :entries` statement, so two
  turns on the same session arriving at once both survive. See
  [sessions](/data-model/sessions.md).

  `history_for_llm` **projects each entry to `{role, content}`**, dropping the stored
  `interaction_id`. That is load-bearing rather than tidy: `ai.synthesize_answer`
  renders the history with `json.dumps` over whole entries, so any bookkeeping field
  left on one is sent to the model as noise and re-sent on every later turn. See
  [sessions](/data-model/sessions.md).

  The same module serves [`/api/sessions`](/api/sessions.md):
  `list_sessions(db, *, limit, offset)` → `Page[SessionSummary]`,
  `get_transcript(session_id, db)` → `SessionTranscript | None`, and
  `delete_session(session_id, db)` → `bool`. The two interesting parts are pure
  functions beside them, so they are unit-testable without a database:
  `session_title(first_message)` cuts the opening question to a list-sized label
  on a word boundary, and `transcript_turns(history)` folds the flat entry array
  back into turns **totally** — `history` is untyped JSONB, so an entry that does
  not pair still renders rather than raising.

  **`/api/sessions` is the API's first mutating endpoint.** Every retrieval route
  is read-only and stateless; `DELETE /api/sessions/{id}` is the only route
  anywhere in this package that removes a row.

## Search/browse/traversal service layer (`api/services/`)

Every function here takes `(AsyncSession, a typed pydantic model)` and returns typed
pydantic models — never a FastAPI `Request`/`Response` — so the same call works from a
route, a test, or a future MCP tool wrapper. See [deterministic
search](/retrieval/deterministic-search.md) for why.

- **`search_service.py`** — `search_documents(query: SearchQuery, session, *,
  embedding_provider, settings, llm_provider=None) -> SearchResponse` and
  `get_filters(session) -> DocumentFacets`. Implements
  [`POST /api/search`](/api/search.md) and [`GET /api/filters`](/api/filters.md).
  Every repository call here awaits in sequence: one `AsyncSession` serves the
  whole request and permits one operation at a time, so gathering the search arms
  raises `InvalidRequestError` rather than saving time. This holds for any service
  in this package, not just this one.
- **`document_service.py`** — `list_documents`, `get_document_detail`,
  `get_document_chunks`, `get_document_pdf`. Implements
  [`GET /api/documents`](/api/documents.md),
  [`GET /api/documents/{id}`](/api/document-detail.md),
  [`GET /api/documents/{id}/chunks`](/api/document-chunks.md) and
  [`GET /api/documents/{id}/pdf`](/api/document-pdf.md).
- **`concept_service.py`** — `list_concepts`, `list_documents_for_concept`. Implements
  [`GET /api/concepts`](/api/concepts.md) and
  [`GET /api/concepts/{id}/documents`](/api/concept-documents.md).
- **`keyword_service.py`** — `list_keywords`, `list_documents_for_keyword`. Reuses the
  entity repos with `entity_type` pinned to `EntityType.KEYWORD` rather than owning
  storage of its own; kept as a separate service from `concept_service.py` because the
  two answer different questions (declared vs. inferred — see
  [entities](/data-model/entities.md)). Implements
  [`GET /api/keywords`](/api/keywords.md) and
  [`GET /api/keywords/{id}/documents`](/api/keyword-documents.md).

## FastAPI app (`api/main.py`)

`create_app() -> FastAPI`. The lifespan handler calls `ai.install_file_tracing()`
first — it takes no storage backend, since [LLM traces](/observability.md) are local
files, unrelated to `app.state.storage` — so the dimension probe below is recorded
like any other billed embedding call. It then sets `app.state.storage` and
`app.state.embedding_provider` at startup (and runs `ai.verify_embedding_dimension` — see
[embedding dimension](/decisions/embedding-dimension.md)), then constructs one provider
per [role](/reference/llm-config.md): `structured`, `chat`, `read` and `sql`. The chat
agent uses two of them — `chat` drives its loop and writes the answer, `read` is the
sub-agent it hands a whole decision to. Routes: the search, documents, concepts,
keywords and sql routers are registered ahead of the chat router, plus `GET /healthz`.

Each lifespan stage logs at DEBUG as it completes, and the whole sequence logs one INFO
line — elapsed seconds, storage backend, embedding dimension, resolved `LOG_LEVEL` — when
the app is ready to serve. The embedding-provider stage is timed on its own: a warm-cache
local model still costs ~9s there and a cold or revalidating one ~90s, long enough to
read as a hang without it. See [Application Logging](/logging.md).

`create_app()` registers `AccessLogMiddleware` before `CORSMiddleware`, so — middleware
runs outermost-added-last — CORS wraps the access log and answers a preflight `OPTIONS`
itself, before it would otherwise reach the log.

CORS is configured from `AppSettings.api_cors_origins`, and names
`X-Interaction-Id` in `expose_headers`. That is a separate requirement from the
permissive `allow_headers`, which governs the request direction only: a browser cannot
read a response header the server has not exposed, so without it the correlation id
reaches the browser and stays invisible to it.

## Chat route (`api/routes/chat.py`)

Implements the [chat endpoint](/api/chat-endpoint.md) contract. A thin adapter, like
every other route here: it owns the session, the SSE framing and the turn persistence,
and nothing about how the answer is reached.

| Symbol | Kind | Purpose |
|---|---|---|
| `ChatRequest` | Pydantic model | `session_id: UUID \| None`, `message: str` (1–4000 chars) |
| `_format_sse(event, data)` | pure function | Produces an `event: …\ndata: …\n\n` frame |
| `_pdf_url(document_id)` | pure function | The [PDF endpoint's](/api/document-pdf.md) path, added to each source |
| `chat_endpoint` | route handler | Session + toolset + `run_chat_agent()` + SSE; dispatches via `match`/`case` over `AgentEvent` |

Request flow: validate `ChatRequest` (422 on empty/long/bad `session_id`) →
`build_chat_toolset` → `get_or_create_session` → `db.commit()` (see [why the row commits
before the turn does](/data-model/sessions.md#a-row-exists-before-the-conversation-does))
→ `history_for_llm` → `run_chat_agent`
(async generator) → `_format_sse` each event → `StreamingResponse`
(`text/event-stream`, headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`); the
`done` frame carries the `session_id`, and the turn is persisted after it. The DB
session comes from `api/dependencies.get_db`, shared with every other router.

The one branch in it: when `CHAT_SCRIPT` names a script, `run_chat_agent` is
replaced by `replay(SCRIPTS[…])` from `api/dev/chat_scripts.py` and neither the
toolset nor the LLM providers are built. Nothing downstream of that assignment
changes, which is the point — see below.

## Scripted chat (`api/dev/chat_scripts.py`)

Development-only fixtures for [agent mode](/frontend/overview.md): canned event
sequences with the pauses between them, replayed in place of the agent so the
client can be looked at without a model run.

| Symbol | Kind | Purpose |
|---|---|---|
| `ScriptedFrame` | frozen dataclass | One `AgentEvent` and the delay before it |
| `stream_text(text)` | pure function | Splits prose into one token frame per word, spaces kept |
| `select_script(setting, message)` | pure function | Which script this turn plays, or `None` for the real agent. Exhaustive `match` over `ChatScript` |
| `SCRIPTS` | dict | `research`, `direct`, `error` |
| `replay(frames)` | async generator | `AsyncIterator[AgentEvent]` — the same type `run_chat_agent` returns |

The frames are built from the DTOs in `agents.chat`, not from dicts, so a
renamed `ProgressLabel` breaks them at import rather than letting a fixture
drift from the contract it stands in for. Between them the three scripts cover
every `ProgressLabel` member, which a unit test asserts. `direct` emits no
`tool_call`/`tool_result` frames at all — a no-tool reply is genuinely
stepless, so the fixture that stands in for it is too — just `sources` (empty),
a `token` and `done`.

## Sessions routes (`api/routes/sessions.py`)

The read and delete half of the chat surface — [contract](/api/sessions.md). Three
thin adapters over `session_service`: a `Page[SessionSummary]` list, a
`SessionTranscript` by id, and a `DELETE` returning 204 or 404. They use the same
`clamp_limit` + `Page[T]` paging as `keywords.py`, and the same `get_db`.

Worth stating where the rest of this package's design notes are: **these are the
only routes that are not read-only.** Everything else here answers questions about
a corpus it never touches.

## Search, document, concept and keyword routes (`api/routes/`)

`search.py`, `documents.py`, `concepts.py` and `keywords.py` are thin adapters: each
route validates input, calls one service function, and either returns its pydantic model
directly or raises `HTTPException`. Full wire contracts are documented per endpoint under
[API](/api/index.md).

## API server design decisions

- **Error event instead of mid-stream HTTP error (chat only):** once a
  `StreamingResponse` starts, headers are sent, so a failure emits `event: error`
  (generic safe message) and stops; `done` is absent and the failed turn is not
  persisted. The agent emits its own `ErrorEvent` for failures it handles, and the route
  catches anything that escapes — either way the client sees one terminal frame. The
  search/documents/concepts routes are plain request/response, so they use ordinary HTTP
  status codes throughout.
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
