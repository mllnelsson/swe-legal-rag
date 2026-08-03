---
type: Table
title: sessions (optional)
description: Conversation history for the deprecated chat surface's follow-up support; can live in-memory or Redis instead when cross-restart persistence isn't needed.
resource: postgres://sessions
tags: [data-model, table, sessions, chat, deprecated]
timestamp: 2026-08-03T00:00:00Z
---

# `sessions` (optional)

Conversation history for follow-up support. Can live in-memory or Redis instead if
cross-restart persistence isn't needed.

This table serves only the [chat endpoint](/api/chat-endpoint.md), which is now
**deprecated but retained**. It is part of the [clean extraction
set](/packages/api.md) and moves with the chat surface when it is lifted into a
future `agent` package; no retrieval endpoint or service touches it.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| created_at | TIMESTAMPTZ | |
| last_active_at | TIMESTAMPTZ | For TTL cleanup |
| history | JSONB | Array of message objects `[{role, content, timestamp}]` |

Backs the multi-turn behaviour of the [chat endpoint](/api/chat-endpoint.md); only the
most recent `SESSION_MAX_HISTORY_TURNS` are passed to the LLM while the full history
stays in this table.
