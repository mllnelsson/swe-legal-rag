# Frontend Design Spec: Överklagandenämnden Decision Search Tool

## Tooling

- **React + Vite**
- **Tailwind CSS + shadcn/ui**
- **Deployed on Cloud Run**

## Interaction Model

Single-page chat interface. User types a question in Swedish, receives a streamed synthesized answer with source citations. No manual filters in V1.

## Core Components

- **Chat view** — Message thread. User messages and agent responses. Scrollable history within a session.
- **Message bubble (agent)** — Streamed markdown/text answer with inline citation markers (case numbers as clickable references). Tokens render as they arrive via SSE.
- **Source cards** — Expandable cards attached to an agent response. Show case number, date, decision outcome, and a short excerpt. Click-through opens or downloads the original PDF. Rendered after the streamed answer completes (sources arrive as a final SSE event or a structured trailer).
- **Input bar** — Text input with send. Supports enter-to-send. Disabled while streaming. Nothing else in V1.
- **Loading/streaming state** — Typing indicator until first token arrives, then live token rendering.

## API Contract

```
POST /api/chat → SSE stream
Request:
{
  "session_id": "uuid | null",
  "message": "string"
}

SSE events:
event: token
data: {"text": "partial token"}

event: sources
data: {"sources": [
  {
    "case_number": "string",
    "decision_date": "date",
    "decision_outcome": "string",
    "category": "string",
    "excerpt": "string",
    "pdf_url": "string"
  }
]}

event: done
data: {"session_id": "uuid"}
```

All LLM interaction is streamed end-to-end: API streams from the LLM provider, SSE streams to the client. No buffering the full response server-side.

## State Management

Minimal. Session history lives on the backend. Frontend holds current session ID and the message list for display. No global state library needed — React state or useReducer is sufficient.

## Deployment

Cloud Run service. Vite builds static assets, lightweight container serves them (nginx or simple node server). Same deploy pattern as backend services.

## Future Enhancements (V2)

- Structured filter sidebar (date picker, category dropdown)
- Mobile-responsive layout
- Dark mode
