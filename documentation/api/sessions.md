---
type: API Endpoint
title: Sessions Endpoints (GET/DELETE /api/sessions)
description: The read and delete contract for past conversations — a summary list that never loads a transcript, a transcript that carries no evidence because none is stored, the empty-history filter, and the single-user model that means every conversation is listed to everyone.
resource: GET /api/sessions
tags: [api, sessions, chat, contract]
timestamp: 2026-08-25T00:00:00Z
---

# Sessions Endpoints (`/api/sessions`)

Reading and forgetting past conversations. Implemented in
`packages/api/src/api/routes/sessions.py` over `session_service`; the state
itself is the [sessions table](/data-model/sessions.md).

**The exception on two counts.** Every retrieval endpoint is stateless and
read-only. `sessions` is the one table the API writes, and `DELETE` here is the
only route in the API that removes anything.

```
GET    /api/sessions              → Page[SessionSummary]
GET    /api/sessions/{id}         → SessionTranscript      404 if unknown
DELETE /api/sessions/{id}         → 204                    404 if unknown
```

## Every conversation is listed to everyone

There is no owner filter because there are no accounts. This is a single-user
tool ([PRD](/prd.md): fewer than ten administrators, no auth in V1), so the list
is the whole table. That is a product decision rather than an oversight, and
[agent mode](/frontend/overview.md) states it on screen rather than leaving it
to be discovered when someone else's question appears in the panel.

## A summary is not a transcript

```json
{
  "id": "uuid",
  "created_at": "timestamp",
  "last_active_at": "timestamp",
  "title": "string",
  "turn_count": 3
}
```

`SessionSummary` is deliberately a different type from `SessionRead` rather than
a subset of it. A conversation's `history` is every question and every full
answer it holds; drawing a sidebar is no reason to load fifty of them. The
projection happens **in SQL** — `jsonb_extract_path_text(history, '0',
'content')` for the opening question, `jsonb_array_length` for the size — so the
JSONB column never crosses the wire to build a list.

`title` is **the first question, verbatim**, whitespace-collapsed and cut to 60
characters on a word boundary. No model writes it: a generated label would put
text in the navigation that the reader cannot check, and cost a call per
conversation to do it. `turn_count` rounds a half-stored turn up rather than
losing it.

Ordering is `last_active_at DESC`. There is no index behind that and none is
needed at this size; if the table ever grows, [indexes](/data-model/indexes.md)
is where one goes.

### Conversations that never happened are absent

`WHERE jsonb_array_length(history) > 0`, and it is load-bearing rather than
tidy. [`POST /api/chat`](/api/chat-endpoint.md) creates the session row *before*
the agent runs and appends the turn only after `done`, so a failed turn, a
turn the user stopped, and a request rejected at validation each leave a row
behind with an empty history. Without the filter the list fills with untitled
blanks, one per thing that went wrong.

## A transcript carries no evidence

```json
{
  "id": "uuid",
  "created_at": "timestamp",
  "last_active_at": "timestamp",
  "turns": [{ "question": "…", "answer": "…", "interaction_id": "uuid | null" }]
}
```

The stored history is a flat `[{role, content, interaction_id}]` array; the
endpoint folds it back into the turns it was appended as. The folding is
**total, not strict** — `history` is untyped JSONB and the pairing is a
convention `append_turn` upholds rather than something Postgres enforces, so an
entry that does not fit still renders as something. A row written by an older
version of this code is a display problem, not a reason to fail a request.

**Only the question and the answer were ever stored.** The passages, the
reader's extracts and the SQL rows a turn gathered are not, which is what stops
turn two re-sending turn one's documents — see
[sessions](/data-model/sessions.md). So a reopened conversation genuinely has no
citations, and a client must **say so** rather than render an empty source list:
"this answer cited nothing" and "we did not keep what it cited" are different
claims and only the second is true. That is [honesty rule
21](/frontend/honesty-rules.md).

`interaction_id` survives, so a bad answer found months later is still a lookup
into the [trace stream](/observability.md).

## Deleting

No soft delete, no confirmation token. The row holds one person's own questions,
nothing else references it, and the traces its turns produced are keyed by
`interaction_id` in file storage — they outlive the row. What is lost is the
transcript, not the record of what the turns cost.

A delete that matched no row is **404**, not a cheerful 204: a client that
pruned nothing should not believe it pruned something.

## Continuing a conversation

Nothing here resumes anything. A client that reopened a conversation sends its
id as `session_id` on the next [`POST /api/chat`](/api/chat-endpoint.md), and
the agent is given the last `SESSION_MAX_HISTORY_TURNS` turn-pairs as usual. A
reopened conversation and one that was never left are the same thing to the
agent.
