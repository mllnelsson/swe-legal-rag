---
type: Concept
title: Frontend
description: The V1 single-page streaming chat UI (React/Vite/Tailwind/shadcn) and how it consumes the chat endpoint.
tags: [frontend, ui, chat, v1]
timestamp: 2026-07-24T00:00:00Z
---

# Frontend

## Tooling

- **React + Vite**
- **Tailwind CSS + shadcn/ui**
- **Deployed on Cloud Run**

## Interaction Model

Single-page chat interface. User types a question in Swedish, receives a streamed
synthesized answer with source citations. No manual filters in V1.

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
