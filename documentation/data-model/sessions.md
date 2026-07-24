---
type: Table
title: sessions (optional)
description: Conversation history for follow-up support; can live in-memory or Redis instead when cross-restart persistence isn't needed.
resource: postgres://sessions
tags: [data-model, table, sessions, chat]
timestamp: 2026-07-24T00:00:00Z
---

# `sessions` (optional)

Conversation history for follow-up support. Can live in-memory or Redis instead if
cross-restart persistence isn't needed.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| created_at | TIMESTAMPTZ | |
| last_active_at | TIMESTAMPTZ | For TTL cleanup |
| history | JSONB | Array of message objects `[{role, content, timestamp}]` |

Backs the multi-turn behaviour of the [chat endpoint](/api/chat-endpoint.md); only the
most recent `SESSION_MAX_HISTORY_TURNS` are passed to the LLM while the full history
stays in this table.
