---
type: Table
title: sessions
description: Conversation history backing the chat endpoint's follow-up support and the conversation list, plus the agent's own carry-over notes; the transcript holds the question and the answer only, never the evidence a turn gathered.
resource: postgres://sessions
tags: [data-model, table, sessions, chat]
timestamp: 2026-08-28T00:00:00Z
---

# `sessions`

Conversation history: the follow-up support behind the [chat
endpoint](/api/chat-endpoint.md), and the conversations the
[sessions endpoints](/api/sessions.md) list, reopen and delete.

**Durable, not a cache.** Reopening a conversation from last week is a feature,
so this has to survive a restart — an in-memory or Redis version of it would not
be the same table with different plumbing, it would be a different product.

It serves those two surfaces and nothing else — no retrieval endpoint or service
touches it. It is the one piece of state in an otherwise stateless API, and the
only table anything here writes or deletes: the [conversational
agent](/retrieval/chat-agent.md) itself keeps nothing between requests, and
`session_service` in the [api package](/packages/api.md) owns every read and
write.

**No owner column, deliberately.** There are no accounts, so every row is
visible to whoever opens the app — see [the sessions
endpoints](/api/sessions.md#every-conversation-is-listed-to-everyone).

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| created_at | TIMESTAMPTZ | |
| last_active_at | TIMESTAMPTZ | For TTL cleanup |
| history | JSONB | Array of message objects `[{role, content, interaction_id}]` — the transcript a user sees |
| context | JSONB | The agent's carry-over blob (`{}` by default) — its working notes about the conversation, never shown to a user |

Backs the multi-turn behaviour of the [chat endpoint](/api/chat-endpoint.md); only the
most recent `SESSION_MAX_HISTORY_TURNS` are passed to the LLM while the full history
stays in this table.

**Only the question and the answer are stored in `history`** — never the passages,
document extracts or query results a turn gathered along the way. Persisting the
evidence would mean re-sending turn one's documents on turn two, and it is the
agent's job to gather what the current question needs.

**`context` is a different kind of state, and no relation to `history`
beyond living on the same row.** It is the [conversational
agent's](/retrieval/chat-agent.md#carry-over-context) own carry-over — a JSON
blob a turn reads at the start of its plan step and a turn may hand back
updated at the end — read and written through
`api.services.context_store.PostgresContextStore`, which implements
`agent_kit.ContextStore` against `get_context`/`set_context` below. Unlike
`history`, nothing renders it: a client never sees this column's contents.
The default `derive_context` this app wires up
(`agents.chat.chat_context_carry`) accumulates the case numbers a conversation
has surfaced, so a later turn's planner has continuity without re-retrieving.

`interaction_id` is stored on both entries of a turn — it is the same id the
`X-Interaction-Id` response header carried for that request, so a turn found in a
session is a lookup into the [trace stream](/observability.md), not a timestamp guess.
It is bookkeeping, not something a model should see: `history_for_llm()` projects each
entry down to `{role, content}` before a prompt sees it. This is load-bearing, not
tidiness — `ai.synthesize_answer` renders the whole history with `json.dumps`, so any
field left on a stored entry would be sent to the model as noise, and re-sent again on
every later turn.

## Appending a turn

`history` is appended to **by Postgres**, in one statement — the `append_history`
[repository function](/data-model/repositories.md) issues
`UPDATE sessions SET history = history || :entries::jsonb`. Nothing reads the array
first.

That is a correctness requirement, not an optimisation. Reading the array into Python
and writing it back loses a turn whenever two arrive at once: both read the same
history, both write their own version, and whichever commits last erases the other. A
`SELECT ... FOR UPDATE` would also be wrong here for a second reason — the append runs
after the SSE stream has finished, inside the request-scoped session, so the row lock
would be held for the whole turn, which [NFR1b](/prd.md) budgets at up to a minute.

Two consequences fall out: a missing session needs no pre-check, because the `WHERE`
clause simply matches no row; and the read side is unaffected, since each request
already loads its history once at the start and the append only ever adds to the end.

## Reading and writing the context blob

`session.get_context(session, session_id)` reads `context` and returns a copy —
`{}` for a missing session — so a caller free to mutate what it gets back
cannot reach into the ORM instance behind it. `session.set_context(session,
session_id, context)` **replaces** the whole blob with one `UPDATE ... SET
context = :new_context`, unlike `append_history`'s append: the blob has no
append-only shape to preserve, and the caller (`chat_context_carry`, or
whatever `derive_context` a host passes) already computed the value the row
should hold next. Like `append_history`, it takes no row lock and a missing
session is a no-op.

## A row exists before the conversation does

`get_or_create_session` writes the row when the request arrives, and
`append_turn` runs only after the turn reaches `done`. So a failed turn, a turn
the user stopped mid-answer, and a request rejected at validation each leave a
row with `history = []` behind.

The route commits that row immediately, rather than leaving it flushed-only
until the request's teardown once the whole turn finishes. The turn itself can
run for up to a minute, but the `done` frame that names the session to the
client fires just before the request ends — so without the early commit, a
client that claims the id as a URL and refetches [the session
list](/api/sessions.md) the instant `done` arrives could still beat the
teardown's commit on the original connection and read a 404 for a conversation
it had just been told the name of.

Those are not conversations, and [the list](/api/sessions.md) filters them out
with `jsonb_array_length(history) > 0`. Nothing cleans them up: they cost a row
each and are what a TTL sweep over `last_active_at` would take first.

## Reading it without reading all of it

The conversation list needs a title and a size, not a transcript. Both are
projected in SQL — `jsonb_extract_path_text(history, '0', 'content')` and
`jsonb_array_length(history)` — so listing conversations never pulls this column
into Python. `SessionSummaryRow` in `shared/dtos/session.py` is that projection;
`SessionRead`, which carries the whole array, is for the two callers that
genuinely need it.
