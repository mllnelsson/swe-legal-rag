---
type: API Endpoint
title: Chat Endpoint (POST /api/chat)
description: Deprecated but retained — the POST /api/chat Server-Sent Events contract — request shape, streamed token/sources/done events, and mid-stream error semantics.
resource: POST /api/chat
tags: [api, sse, chat, contract, deprecated]
timestamp: 2026-08-03T00:00:00Z
---

# Chat Endpoint (`POST /api/chat`)

## Deprecated — retained, not deleted

`POST /api/chat` renders as `deprecated` in the OpenAPI schema and Swagger UI. The
`api` package's purpose is a deterministic retrieval tool set — the [search,
documents and concepts endpoints](/api/index.md) reach the corpus with no LLM in
the request path except the query embedding and the opt-in [query
expander](/retrieval/query-expansion.md). This endpoint is the one surface left that
is LLM-driven, stateful (sessions) and streaming — the agent, not the tool set —
and is expected to move to a future `agent` package that consumes the retrieval API
rather than living beside it. See [the api package](/packages/api.md) for the exact
extraction set.

This is an ownership marker, not a compatibility window: [nothing is
deployed](/reference/deployment-state.md), so there is no consumer to give migration
time to. It is deprecated rather than deleted because it is working, tested code the
future agent will want intact. Nothing below this section has changed — the contract
still behaves exactly as described.

The single wire contract between the [frontend](/frontend/overview.md) chat UI and the
backend. All LLM interaction is streamed end-to-end: the API streams from the LLM
provider and re-streams to the client over SSE. The full response is never buffered
server-side.

## Request

```json
{
  "session_id": "uuid | null",
  "message": "string"
}
```

A null `session_id` starts a new session; a supplied one continues an existing
conversation (see [sessions](/data-model/sessions.md)).

## SSE events (happy path)

```
event: token
data: {"text": "partial token"}

event: sources
data: {"sources": [
  {
    "case_number": "string",
    "decision_date": "date",
    "decision_outcome": "string",
    "category": "string",
    "excerpt": "string",
    "pdf_url": "string",
    "section": "body | appendix",
    "appendix_label": "string | null"
  }
]}

event: done
data: {"session_id": "uuid"}
```

`token` events stream as the synthesized answer is produced. The `sources` event
carries the cited decisions and arrives after the answer text. `done` terminates a
successful turn and returns the (possibly newly created) `session_id`.

`section` says which part of the PDF the excerpt is quoting.
**`"appendix"` means the appealed decision** — the lower instance's words, which
Överklagandenämnden may have overturned — and `appendix_label` names it (`"Bilaga A"`).
A client must not present such an excerpt as the nämnd's own reasoning. Body excerpts
are the default; appendices only appear when the query planner judged the question to be
about the appealed decision, or when body-only retrieval found nothing. See
[body-first retrieval](/decisions/body-first-retrieval.md).

## Error semantics

**Mid-stream failure.** If the LLM provider or retrieval fails after the response
stream has started (headers already sent), the server emits an in-band error rather
than an HTTP error code:

```
event: error
data: {"message": "human-readable error summary"}
```

`event: done` is **absent** on error — the client treats `event: error` as terminal
and never expects a `done` after it. The failed turn is not saved to session history.

**Pre-stream validation.** Validation errors detected before streaming begins (empty
message, invalid `session_id`) return a normal **HTTP 422** and no SSE stream is
opened.

The retrieval and synthesis behind this endpoint is the [query/retrieval
agent](/retrieval/agent.md); the endpoint is served by the [api
package](/packages/api.md).
