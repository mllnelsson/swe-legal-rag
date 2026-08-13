---
type: Table
title: sessions (optional)
description: Conversation history backing the chat endpoint's follow-up support; holds the question and the answer only, never the evidence a turn gathered.
resource: postgres://sessions
tags: [data-model, table, sessions, chat]
timestamp: 2026-08-13T01:00:00Z
---

# `sessions` (optional)

Conversation history for follow-up support. Can live in-memory or Redis instead if
cross-restart persistence isn't needed.

This table serves only the [chat endpoint](/api/chat-endpoint.md) — no retrieval
endpoint or service touches it. It is the one piece of state in an otherwise stateless
API: the [conversational agent](/retrieval/chat-agent.md) itself keeps nothing between
requests, and `session_service` in the [api package](/packages/api.md) owns every read
and write.

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
