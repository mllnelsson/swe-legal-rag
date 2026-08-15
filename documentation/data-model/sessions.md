---
type: Table
title: sessions
description: Conversation history backing the chat endpoint's follow-up support and the conversation list; holds the question and the answer only, never the evidence a turn gathered.
resource: postgres://sessions
tags: [data-model, table, sessions, chat]
timestamp: 2026-08-15T00:00:00Z
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
| history | JSONB | Array of message objects `[{role, content, interaction_id}]` |

Backs the multi-turn behaviour of the [chat endpoint](/api/chat-endpoint.md); only the
most recent `SESSION_MAX_HISTORY_TURNS` are passed to the LLM while the full history
stays in this table.

**Only the question and the answer are stored** — never the passages, document extracts
or query results a turn gathered along the way. Persisting the evidence would mean
re-sending turn one's documents on turn two, and it is the agent's job to gather what
the current question needs.

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

## A row exists before the conversation does

`get_or_create_session` writes the row when the request arrives, and
`append_turn` runs only after the turn reaches `done`. So a failed turn, a turn
the user stopped mid-answer, and a request rejected at validation each leave a
row with `history = []` behind.

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
