---
type: API Endpoint
title: Chat Endpoint (POST /api/chat)
description: The POST /api/chat Server-Sent Events contract — a Swedish question in, progress keys then a streamed answer out; the closed label vocabulary a client maps its own words onto, the mandatory sql event, and the terminal error semantics.
resource: POST /api/chat
tags: [api, sse, chat, agent, contract]
timestamp: 2026-08-13T00:00:00Z
---

# Chat Endpoint (`POST /api/chat`)

A Swedish free-text question in; a stream of what the agent is doing, then the
answer it wrote, out. Served by the [conversational
agent](/retrieval/chat-agent.md) in the [agents package](/packages/agents.md);
the route (`packages/api/src/api/routes/chat.py`) owns the session, the SSE
framing and nothing else.

All LLM interaction is streamed end to end: the API streams from the provider
and re-streams to the client. The answer is never buffered server-side.

There is no client for this contract in this repository — the
[frontend](/frontend/overview.md) calls only the deterministic retrieval API.

## Request

```json
{
  "session_id": "uuid | null",
  "message": "string (1-4000 chars)"
}
```

A null `session_id` starts a new session; a supplied one continues an existing
conversation (see [sessions](/data-model/sessions.md)). Stale or unrecognized
ids silently create a fresh session rather than erroring.

## Events

Progress events precede the first token. **Roughly 18 seconds elapse before the
answer starts** — see [latency](#latency) — which is what they are for.

```
event: tool_call     data: {"type","id","tool","label","detail"}
event: tool_result   data: {"type","id","tool","label","status","detail"}
event: sql           data: {"type","answered","sql","columns","rows",
                            "row_count","truncated","assumptions","attempts"}
event: token         data: {"text"}
event: sources       data: {"sources":[…]}
event: done          data: {"session_id"}
event: error         data: {"message"}
```

Ordering: `tool_call`/`tool_result` pairs (with `sql` among them) → `token`* →
`sources` → `done`. A run that finds nothing still emits `token`, `sources` (an
empty list) and `done` — the corpus not addressing a question is an answer.

### The API emits keys; the client owns the words

`label` is a **closed enum owned by the API**. A client maps it to a static
string it holds — "Söker i besluten", "Filtrerar och söker" — and the API never
composes user-facing progress prose. Three consequences: no translation lives in
the backend, a client never parses tool arguments to decide what to display, and
the vocabulary extends without either side guessing.

`label` is deliberately **finer-grained than `tool`**, so one tool can report
more than one kind of step:

| `label` | Tool | Means |
|---|---|---|
| `vocabulary.list` | `list_vocabulary` | Reading the category, outcome and keyword values that occur |
| `search.broad` | `search_decisions` | Searching, no filter |
| `search.filtered` | `search_decisions` | Searching a narrowed set |
| `search.refused` | `search_decisions` | A filter was declined pending grounding |
| `sql.query` | `query_corpus` | Counting or aggregating |
| `decision.read` | `read_decision` | Reading one decision in full |
| `decision.inspect` | `inspect_decision` | Following entities and citations |
| `answer.compose` | `answer` | Selecting the evidence and finishing |

`status` on a `tool_result` is `ok`, `refused` or `error`. **`refused` is not a
failure** — it is a policy decline (an ungrounded filter, a spent reading
budget) that the agent repairs from on its next iteration, and a client should
present it as a step rather than a problem.

`detail` is structured, never prose, and **optional for a client**: it exists so
a later frontend can enrich a label ("7 beslut") without a contract change. `id`
correlates a `tool_call` with its `tool_result`.

**Sub-agent iterations are not surfaced.** `query_corpus` runs the [SQL
agent's](/api/sql-agent.md) own 2–5 iteration loop behind a single
`tool_call`/`tool_result` pair, and `read_decision` one model call behind
another. A client sees one step per tool, not the internals.

**Unknown event types are free.** SSE clients dispatch by event name, so a
consumer listening only for `token`/`sources`/`done` ignores every progress
frame. That is what makes emitting these now and building UI for them later a
non-breaking sequence.

### `event: sql` is an obligation, not a nicety

[The SQL agent's contract](/api/sql-agent.md#the-consumers-obligation) states
that a caller which turns `row_count: 12` into "12 överklaganden avslogs"
without also surfacing `sql` is asserting something it cannot itself verify.
This agent is such a caller, so the generated query, the rows and the full
`attempts` trail reach the client verbatim, before the answer that rests on
them. Unlike the progress events, this one is not decorative.

### `event: sources`

```json
{
  "document_id": "uuid",
  "case_number": "string",
  "decision_date": "date",
  "decision_outcome": "string",
  "category": "string",
  "excerpt": "string (first 200 chars of the cited passage)",
  "section": "body | appendix",
  "appendix_label": "string | null",
  "pdf_url": "/api/documents/{id}/pdf"
}
```

One entry per cited decision, first selected passage winning. `section:
"appendix"` **means the appealed decision** — the lower instance's words, which
Överklagandenämnden may have overturned — and `appendix_label` names it
("Bilaga A"). A client must not present such an excerpt as the nämnd's own
reasoning. See [body-first retrieval](/decisions/body-first-retrieval.md).

`pdf_url` is added by the route, not the agent: it is the [PDF
endpoint's](/api/document-pdf.md) path rather than a storage URL, because the
local backend's `get_url` returns a filesystem path no browser can open.

## Error semantics

**Mid-stream failure.** Once the response stream has started the headers are
sent, so a failure is emitted in band:

```
event: error
data: {"message": "human-readable summary"}
```

`event: done` is **absent** on error — a client treats `error` as terminal and
never waits for a `done` after it. The failed turn is not saved to session
history. The message is deliberately generic; the cause is logged server-side.

**Pre-stream validation.** An empty or over-long `message`, or an unparseable
`session_id`, returns **HTTP 422** and no stream is opened.

## Latency

| Phase | Elapsed | Streams? |
|---|---|---|
| Orchestrator iterations | ~5 × 1.5 s | no |
| `query_corpus` sub-agent | ~6 s | no |
| `read_decision` sub-agent | ~3 s | no |
| **First token** | **~18 s** | — |
| Streamed synthesis | ~6 s | **yes** |

These are estimates from component timings, not a measured benchmark. Exactly
one call per run streams — the final synthesis — because
`LLMProvider.generate_stream` takes no tools and there is no streaming tool-call
path in [llm-core](/packages/llm-core.md).

This is well past the 5-second budget [NFR1a](/prd.md) sets for search, deliberately.
The agent is held to **[NFR1b](/prd.md) instead: a turn under one minute**, with the
progress events making the wait legible rather than removing it. A turn that misses that
ceiling is a thrashing loop, not a slow model — the levers are
`chat_agent_max_iterations` and the two search knobs.

## Session context

Each request creates or loads a [session](/data-model/sessions.md) by
`session_id`; the `done` event returns it and subsequent requests send it back.
`history_for_llm()` truncates to the last `SESSION_MAX_HISTORY_TURNS` turn-pairs
before the agent sees it.

**Only the question and the answer are persisted.** The evidence a turn gathered
is not, which is what stops turn two re-sending turn one's documents.
