---
type: Table
title: sessions (optional)
description: Conversation history backing the chat endpoint's follow-up support; holds the question and the answer only, never the evidence a turn gathered.
resource: postgres://sessions
tags: [data-model, table, sessions, chat]
timestamp: 2026-08-13T00:00:00Z
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
| history | JSONB | Array of message objects `[{role, content, timestamp}]` |

Backs the multi-turn behaviour of the [chat endpoint](/api/chat-endpoint.md); only the
most recent `SESSION_MAX_HISTORY_TURNS` are passed to the LLM while the full history
stays in this table.

**Only the question and the answer are stored** — never the passages, document extracts
or query results a turn gathered along the way. Persisting the evidence would mean
re-sending turn one's documents on turn two, and it is the agent's job to gather what
the current question needs.
