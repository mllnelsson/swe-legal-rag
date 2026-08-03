---
type: Concept
title: Frontend
description: The V1 single-page streaming chat UI (React/Vite/Tailwind/shadcn) and how it consumes the now-deprecated chat endpoint.
tags: [frontend, ui, chat, v1]
timestamp: 2026-08-03T00:00:00Z
---

# Frontend

## Tooling

- **React + Vite**
- **Tailwind CSS + shadcn/ui**
- **Deployed on Cloud Run**

## Interaction Model

Single-page chat interface. User types a question in Swedish, receives a streamed
synthesized answer with source citations. No manual filters in V1.

V1's scope is a frontend decision, not a backend limitation. The
[retrieval API](/api/index.md) already serves the filtered, browsable and
traversable surface the backlog below describes: explicit metadata filters on
[search](/api/search.md), a filter vocabulary to populate the controls
([`/api/filters`](/api/filters.md)), metadata-only browse
([`/api/documents`](/api/documents.md)), and click-through from a decision to its
legal concepts and cited cases ([document detail](/api/document-detail.md),
[concept documents](/api/concept-documents.md)). Building the sidebar is a
frontend task with no backend work in front of it.

## Core Components

- **Chat view** — Message thread. User messages and agent responses. Scrollable
  history within a session.
- **Message bubble (agent)** — Streamed markdown/text answer with inline citation
  markers (case numbers as clickable references). Tokens render as they arrive via SSE.
- **Source cards** — Expandable cards attached to an agent response. Show case number,
  date, decision outcome, and a short excerpt. Click-through opens or downloads the
  original PDF. Rendered after the streamed answer completes (sources arrive as a final
  SSE event or a structured trailer).
- **Input bar** — Text input with send. Supports enter-to-send. Disabled while
  streaming. Nothing else in V1.
- **Loading/streaming state** — Typing indicator until first token arrives, then live
  token rendering.

## API Contract

The frontend consumes the [chat endpoint](/api/chat-endpoint.md) — `POST /api/chat`
over Server-Sent Events. The `token` / `sources` / `done` events drive live rendering;
an in-band `event: error` is treated as terminal, and pre-stream validation surfaces as
HTTP 422. See that concept for the full contract.

That endpoint is now **deprecated but retained**: it still behaves exactly as
described and the V1 UI keeps consuming it unchanged. The forward path for a
non-chat frontend is the [retrieval API](/api/index.md) paragraph above — a future
UI would call search/documents/concepts directly rather than through the chat agent.

## State Management

Minimal. Session history lives on the backend. Frontend holds the current session ID
and the message list for display. No global state library needed — React state or
`useReducer` is sufficient.

## Deployment

Cloud Run service. Vite builds static assets; a lightweight container serves them
(nginx or a simple node server). Same deploy pattern as the backend services.

## Future Enhancements (V2)

- Structured filter sidebar (date picker, category dropdown)
- Mobile-responsive layout
- Dark mode
