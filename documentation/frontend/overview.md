---
type: Concept
title: Frontend
description: The React SPA at frontend/ — two surfaces over the same corpus: deterministic search, and agent mode, an SSE client for the conversational agent. No LLM call is made from the browser; both surfaces go through the API.
tags: [frontend, ui, search, agent, sse, react, spa]
timestamp: 2026-08-15T00:00:00Z
---

# Frontend

A React single-page app at `frontend/` in this repo, with **two surfaces over
the same corpus**:

* **Search** (`/`, `/sok`) — the deterministic [retrieval
  API](/api/index.md): filters, documents, concepts, keywords. Every word on
  screen is either the nämnd's own text or a label this app wrote.
* **Agent mode** (`/agent`) — an SSE client for
  [`POST /api/chat`](/api/chat-endpoint.md), described below.

They are separate surfaces because they make different promises to the reader,
and which one runs is the reader's explicit choice rather than something
inferred from how a question is worded.

**The browser makes no LLM call and holds no agent logic.** Agent mode POSTs a
question and renders what comes back; the decomposition, the retrieval, the
tool loop and the writing all happen behind the API.

## Stack

Vite + React 19 + TypeScript, `react-router` for routing, TanStack Query for
server state, Vitest + Testing Library for tests. Styling is plain CSS against
the [design system](#design-system)'s custom properties — no Tailwind, no
shadcn/ui, no CSS framework. 15 direct dependencies total; the runtime set is
just `react`, `react-dom`, `react-router`, `@tanstack/react-query`.

## Routes

| Path | Page |
|---|---|
| `/` | Search home — carries the **Sök / Agent** mode toggle |
| `/sok` | Search results |
| `/agent` | Agent mode; `?q=` hands over a question from the home page and is dropped on arrival |
| `/beslut/:documentId` | Decision detail |
| `/sokord` | Keyword (Sökord) index |
| `/sokord/:entityId` | Decisions carrying one keyword |
| `/begrepp` | Concept index |
| `/begrepp/:entityId` | Decisions carrying one concept (`?typ=` scopes the entity type) |
| `/stil` | Dev-only component reference, not linked from app navigation |

All search filter state lives in the `/sok` query string, in
`src/features/search/search-params.ts`'s pure parse/serialize functions —
Swedish param names (`q`, `sokord`, `kategori`, `utfall`, `fran`, `tom`,
`refs`, `sida`) matching the interface's language — so every search is a
shareable, bookmarkable URL and nothing about the current search lives only in
React state.

## Agent mode

`/agent` is the client for [`POST /api/chat`](/api/chat-endpoint.md). Three
files carry it:

| File | Job |
|---|---|
| `src/api/chat-events.ts` | The event contract, as TypeScript |
| `src/api/chat-stream.ts` | `openChatStream` — fetch, then an SSE parser over the response body |
| `src/features/agent/` | The hook, the reducer and the components |

**Why fetch and not `EventSource`.** The question travels in a request body and
`EventSource` only issues GETs. Doing it by hand is also what lets the client
abort mid-answer and read the `X-Interaction-Id` response header.

`openChatStream` awaits the response before returning, so a pre-stream refusal
(HTTP 422 on an over-long message) raises `ApiError` like any other API call.
Everything after that arrives in band, failures included.

**Frames are dispatched by SSE event name, not by `data.type`.** The route dumps
whole models for `tool_call`/`tool_result`/`sql`, which therefore carry `type`,
and reshapes `token`/`sources`/`done`/`error`, which do not. An unrecognised
event name is skipped rather than thrown on — the contract says new event types
may be added.

### The progress labels are the client's to translate

`ProgressLabel` is a closed enum the API owns, and the Swedish words for it live
in `src/features/agent/progress-text.ts`. Nothing type-checks that pairing
across the language boundary, so `progress-labels.test.ts` reads
`packages/agents/src/agents/chat/_dtos.py` as text and fails when the backend
adds a label the client has no words for. A label that reaches the client
unrecognised anyway renders neutral prose, never the raw key.

### Conversation state

`session_id` is held in React state for the length of the visit: `null` on the
first message, then whatever the `done` frame returned. **The client never
re-sends the history** — the server holds it and the request carries one
message. A reload starts a new conversation; listing and reopening earlier ones
needs read endpoints the API does not have.

An **aborted turn is not persisted**, because the API appends a turn only after
`done`. The transcript says so rather than showing a turn the agent has no
memory of.

## Generated API types

The TypeScript types the frontend builds against are generated, never hand
written — see [generated API types](/frontend/generated-types.md).

**The chat events are the one exception, and deliberately so.** `/api/chat`
returns a `StreamingResponse`, so FastAPI publishes its request body and nothing
about what comes back; there is nothing for the generator to read. `chat-events.ts`
is therefore written by hand against
[the chat endpoint contract](/api/chat-endpoint.md), which is the authority for
it, and a mismatch there is caught by tests rather than by the compiler.

## Query expansion

A checkbox above the filter rail — "Sök även på omformuleringar av frågan" — lets a
reader opt into [query expansion](/retrieval/query-expansion.md) (`SearchState.expand`),
off by default. It is the one search control the app cannot answer without a model call:
turning it on sends `expand: true` to [`/api/search`](/api/search.md), which invokes the
`structured` LLM role server-side — the browser itself still makes no LLM call. State is
carried in the URL as `?utoka=1`, so an expanded search stays a shareable link; it
survives `clearFilters` (it widens the search rather than narrowing it) and is
deliberately not counted among the active filters. When expansion was requested, the
results summary states whether the extra phrasings shown were generated by a model or,
when the model call failed, that expansion could not be fetched and the search ran on the
query as written.

## Design system

The visual layer is ported from the project's `.claude/skills/design-tools/`
skill. Token CSS (`src/styles/tokens/`) is copied over verbatim, with one
change: `fonts.css`'s Google Fonts `@import` is replaced with self-hosted
`@font-face` rules. Fonts and the 24 Lucide icons used by the app are vendored
into `src/styles/fonts/` and `src/components/display/icon-paths.ts`
respectively, so **no third-party network request leaves the page at
runtime**.

The skill's linting layer (`_adherence.oxlintrc.json`) does not carry over as
shipped: oxlint does not implement the `no-restricted-syntax` rule type the
skill's rules are written as, and 30 of its 33 rules duplicate what TypeScript
already enforces on typed `.tsx` components (the skill's originals are
untyped `.jsx`). The three rules that check something a type system cannot —
no raw colour, no raw spacing value, no font outside the three the system
ships — are reimplemented in `frontend/scripts/check-tokens.mjs`, run by
`npm run lint`.

The skill's components carry US-litigation concepts with no counterpart in
this corpus, and those were dropped rather than mapped: `CitationCard`'s
`authority` (binding/persuasive/secondary) and `treatment` (Followed/
Criticized) fields do not exist here. `Badge` tones are renamed
`declared`/`inferred` instead — see [honesty rule
6](/frontend/honesty-rules.md).

## The honesty rules

The interface makes a set of deliberate, tested claims about what the corpus
data does and does not support — described in full at [honesty
rules](/frontend/honesty-rules.md). They are the domain-specific part of this
app; everything else is fairly generic search UI.

Agent mode adds a harder version of the same question, because the words on
screen are written by a language model rather than lifted from a decision. Rules
13–20 cover it: what a source may be presented as, when a count may be shown,
and how a reader can tell a finished answer from a half-written one.

## Where relevance comes from

`score` is not it. It is the RRF fusion value, and RRF works on rank, so the top
hit of every search scores 0.01639 no matter what was asked — see [honesty rule
4](/frontend/honesty-rules.md). The client reads relevance from three places
instead, all described in [`POST /api/search`](/api/search.md):

* `chunks[].vector_similarity` — cosine similarity, comparable across queries.
  `null` means that chunk matched on words alone.
* `diagnostics.top_vector_similarity` and `diagnostics.vector_similarity_floor` —
  the best similarity the search reached, and the bar it had to clear.
* `diagnostics.text_hit_counts` — all zero means no word of the query occurs
  anywhere in the corpus, so the hits are matches of meaning only. The results
  page says so, and only when there are results to say it about ([honesty rule
  11](/frontend/honesty-rules.md)).

Because the vector arm applies the [similarity
floor](/retrieval/deterministic-search.md#the-similarity-floor), a query the
corpus has nothing close to now returns nothing rather than its nearest
neighbours — which is what makes the "no matches" empty state reachable without
a filter ([honesty rule 3](/frontend/honesty-rules.md)).

## Running it

```
uv run --package api uvicorn api.main:app --reload   # :8000
npm run dev                                            # :5173, in frontend/
```

`:5173` is already the API's default CORS origin, and Vite proxies `/api` to
`:8000`. Embeddings run locally (`embedding.provider: local`), so search
costs time rather than money, but the API still constructs the `structured`/
`chat`/`read`/`sql` LLM roles at startup and needs either `BERGET_API_KEY` or
`LLM_PROVIDER=none` to start. `EMBEDDING_DIMENSION` must agree with
`llm_config.yaml`.

## Out of scope

Not in this version: saved matters or bookmarks, a marketing site, auth, and a
mobile layout.

**Earlier conversations.** Agent mode holds one conversation per visit. The
[sessions table](/data-model/sessions.md) already carries everything a list
would need — `id`, `created_at`, `last_active_at`, `history` — but there is no
endpoint to read it, so listing and reopening past conversations is a separate
piece of work. `/agent` leaves the room for a rail beside the transcript.

A reopened conversation would show text without citations: the API persists the
question and the answer only, never the evidence a turn gathered, which is what
stops turn two re-sending turn one's documents.

## Deployment

Not deployed — see [deployment state](/reference/deployment-state.md).
