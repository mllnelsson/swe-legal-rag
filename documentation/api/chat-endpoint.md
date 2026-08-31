---
type: API Endpoint
title: Chat Endpoint (POST /api/chat)
description: The POST /api/chat Server-Sent Events contract — a Swedish question in, progress keys, sources, then a streamed answer out; the closed label vocabulary a client maps its own words onto, the mandatory sql event, the per-passage sources event a citation marker resolves against, the terminal error semantics, and the X-Interaction-Id correlation header.
resource: POST /api/chat
tags: [api, sse, chat, agent, contract]
timestamp: 2026-08-30T00:00:00Z
---

# Chat Endpoint (`POST /api/chat`)

A Swedish free-text question in; a stream of what the agent is doing, then the
answer it wrote, out. Served by the [conversational
agent](/retrieval/chat-agent.md) in the [agents package](/packages/agents.md);
the route (`packages/api/src/api/routes/chat.py`) owns the session, the SSE
framing and nothing else.

All LLM interaction is streamed end to end: the API streams from the provider
and re-streams to the client. The answer is never buffered server-side.

The client is [agent mode](/frontend/overview.md) in the frontend. Its event
types are hand-written rather than generated: this endpoint returns a
`StreamingResponse`, so nothing about the frames below appears in the OpenAPI
document, which makes this page their authority.

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

Progress events precede the first token. **The plan step and the executor
loop together run for tens of seconds before the answer starts** — see
[latency](#latency) — which is what the progress events are for.

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

Ordering: `tool_call`/`tool_result` pairs (with `sql` among them) → `sources` →
`token`* → `done`. `sources` precedes the prose on every path — the passages
were fixed the moment `answer` was called, and the answer marks its claims with
a passage handle as it streams (`[c3]`), so a marker should be resolvable the
instant it arrives rather than the instant the stream ends. A run that finds
nothing still emits `sources` (an empty list), `token` and `done` — the corpus
not addressing a question is an answer.

### Not every turn is a research question

A greeting, a thank-you, or a question about the previous answer — "förklara det
enklare" — has nothing to retrieve. Such a turn is caught by the plan step
ahead of the executor loop: it calls no tool and writes the reply itself, so no
executor loop and no synthesis call ever run, and the turn reaches the client
with **no step frames whatsoever** — no `tool_call`, no `tool_result`:

```
event: sources       {"sources":[]}
event: token         …
event: done          {"session_id":…}
```

No step, no search, and an empty `sources` list that is the truthful one: the
answer rests on the conversation, not on a decision. Unlike a researched
answer it arrives as one `token` frame rather than many — a caller still reads
it the same way, since a client already has to accumulate `token` frames into
one answer.

The empty `sources` list therefore means two different things depending on the
turn, and both are real answers — "I looked and found nothing" and "there was
nothing to look for". See [the conversational
agent](/retrieval/chat-agent.md#two-ways-a-turn-can-end).

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
| `sql.query` | `query_corpus` | Counting or aggregating |
| `decision.read` | `read_decision` | Reading one decision in full |
| `decision.inspect` | `inspect_decision` | Following entities and citations |
| `answer.compose` | `answer` | Selecting the evidence and finishing |

**A `tool_result` carries the same label as the `tool_call` it closes.** A
declined filter is not a step of its own — `search_decisions` still goes out as
`search.broad` or `search.filtered` and comes back under that same label, and
`status` alone says what happened to it.

`status` on a `tool_result` is `ok`, `refused` or `error`. **`refused` is not a
failure** — it is a policy decline (an ungrounded filter, a spent reading
budget) or a bad tool call the model itself made (an argument name the tool
does not accept, or a missing required one) that the agent repairs from on its
next iteration, and a client should present it as a step rather than a
problem. A bad-argument refusal names the tool's valid arguments in its
message, since a model told only that its call was rejected has no way to
learn which argument was the problem.

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
  "handle": "string, e.g. \"c3\"",
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

One entry per cited **passage**, not per decision — several entries may share a
`document_id`. An entry may originate from a
[reading](/retrieval/chat-agent.md#reading-a-decision-is-a-sub-agent) as well as
a search — both surfaces feed the same handle assignment, so a passage never
gets a second handle just because a reading also pointed at it. `handle` is the
marker the answer's prose carries directly after the claim it supports (`[c3]`,
or `[c3][c7]` when several passages support one sentence); a client resolves a
marker against the entry with the matching `handle` to render an inline
citation, and a marker naming a handle absent from this list (or a reopened
conversation, whose sources were never persisted) has nothing to resolve
against and must not be shown raw. `section: "appendix"`
**means the appealed decision** — the lower instance's words, which
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
history. The message is deliberately generic and in Swedish, whether it
originated in the agent or in the route; the cause is logged server-side.

**Pre-stream validation.** An empty or over-long `message`, or an unparseable
`session_id`, returns **HTTP 422** and no stream is opened.

## Correlation

```
X-Interaction-Id: <uuid>    # request header, optional
X-Interaction-Id: <uuid>    # response header, always present
```

A supplied header is honoured **only when it parses as a UUID**; anything else is
silently ignored and an id is minted instead — the same rule as an unrecognized
`session_id`. The response header always carries the id actually in use, canonicalised,
so a client that supplied a rejected value can tell.

One id spans everything the turn cost — the plan step, the executor's iterations,
both sub-agents and the streamed synthesis — which is what [LLM Observability](/observability.md)
sums cost over and what a reported bad answer is found by later. It is stored on
both entries of the resulting [session](/data-model/sessions.md) turn.

The header carries it rather than the `done` event because response headers are sent
before the stream opens, so the id survives a turn that ends in `event: error` instead.

## Latency

| Phase | Elapsed | Streams? |
|---|---|---|
| Plan step | ~15 s | no |
| Executor iterations | ~2–5 s each | no |
| `query_corpus` sub-agent | ~6 s | no |
| `read_decision` sub-agent | ~3 s | no |
| Streamed synthesis | ~10 s | **yes** |

These are estimates from component timings, not a fixed benchmark — a turn
taking more executor iterations or reading more decisions adds proportionally.
On one live counting turn against the real corpus, the plan step, executor and
synthesis together landed at roughly 55 seconds end to end: the plan step and
synthesis run on the strong `chat` model, and the executor's iterations in
between — the mechanical part of the turn — run on `orchestrate`, a smaller
model, which is what keeps each iteration to single digits. The plan step
precedes the first progress event, so it is spent inside the pre-first-token
wait like everything else in this table. Exactly one call per run streams —
the final synthesis — because `LLMProvider.generate_stream` takes no tools and
there is no streaming tool-call path in [llm-core](/packages/llm-core.md).

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

The route commits a freshly created session row immediately, rather than
leaving it flushed-only until the request tears down at the end of the turn —
see [why](/data-model/sessions.md#a-row-exists-before-the-conversation-does).

**Only the question and the answer are persisted as history.** The evidence a
turn gathered is not, which is what stops turn two re-sending turn one's
documents. A second, distinct column — `sessions.context` — carries the
agent's own scratchpad, its persisted working memory, never shown to the
client and never part of this wire contract: the route passes
`conversation_id=str(session.id)` to `run_chat_agent`, which restores and
persists the pad through a `PostgresContextStore` in the same request-scoped
transaction as the turn's `history` append. See [the scratchpad and cross-turn
recall](/retrieval/chat-agent.md#cross-turn-recall) and
[sessions](/data-model/sessions.md).

Sessions outlive the request that made them and are readable: [`/api/sessions`](/api/sessions.md)
lists, reopens and deletes them. A `session_id` a client got from that list is
just a `session_id` here — the agent cannot tell a conversation that was
reopened from one that was never left.

## Development: a scripted stream

`CHAT_SCRIPT` (default `off`) replaces the agent with a canned sequence of these
same events, played with sleeps between them — for looking at the client without
paying for a model run. **Nothing else about the request changes**: the SSE
framing, the `pdf_url` the route attaches, the `X-Interaction-Id` header, the
session row and the persisted turn are all the real ones, which is what makes it
worth doing at this seam rather than mocking in the browser.

`auto` picks per turn from the message length, so both the research shape and
the no-tool-call shape are reachable without a restart; `error` is reachable
only by name. The fixtures live in
`packages/api/src/api/dev/chat_scripts.py` and are built from the DTOs in
`agents.chat`, so they cannot drift from this contract silently. Every scripted
request logs at WARNING, the answers state that they are fabricated, and the
fake `document_id`s make `pdf_url` 404. See [live
testing](/playbooks/live-testing.md#driving-the-ui-without-a-model).
