---
type: Spec
title: Product Requirements
description: Product requirements for a Swedish-language semantic search and chat tool over Överklagandenämnden legal decisions.
tags: [product, requirements, scope]
timestamp: 2026-08-16T00:00:00Z
---

# Product Requirements

## Problem Statement

Swedish Church legal administrators currently have no effective way to search the
body of decisions published by Överklagandenämnden. Decisions exist as PDFs on a
public endpoint but lack semantic searchability. Finding relevant precedent requires
manual reading.

## Target Users

Church legal administrators. Small user base (<10 concurrent), Swedish-speaking
professionals.

## System Specifications

- **S1:** System ingests PDFs from the public API via a multi-step, queue-based
  [pipeline](/pipeline/overview.md). Each step checkpoints its output. Pipeline is
  idempotent and resumable.
- **S2:** System extracts structured metadata (date, case number, decision outcome,
  category/topic) from each document during ingestion.
- **S3:** System exposes two surfaces: deterministic search at `/` and `/sok`, with
  manual structured filters — category, outcome, a date range, Sökord chips, and a
  references toggle, all carried in the `/sok` query string (`kategori`, `utfall`,
  `fran`, `tom`, `sokord`, `refs`) — and [agent mode](/frontend/overview.md) at
  `/agent`, where the user asks questions in natural Swedish.
- **S4:** On query, an [agent](/retrieval/chat-agent.md) decomposes the user's question —
  extracting implicit structured filters (date, topic, decision type) and semantic
  intent.
- **S5:** Agent applies extracted filters to narrow the corpus, then performs semantic
  retrieval on the reduced set.
- **S6:** Agent synthesizes an answer in Swedish, citing specific decisions with case
  numbers.
- **S7:** User can access the original PDF from cited references.
- **S8:** System supports conversational follow-ups within a session — including
  the ones that need no retrieval at all. A greeting, a thank-you or "förklara
  det enklare" is answered from the conversation, without a search; see [the two
  ways a turn can end](/retrieval/chat-agent.md#two-ways-a-turn-can-end).

## Non-Functional Requirements

- **NFR1a:** Deterministic search (`POST /api/search`) responds in **< 5s**. This is the
  latency-sensitive path, and the frontend's search surface — a search box that takes
  longer is a broken search box.
- **NFR1b:** A [conversational agent](/retrieval/chat-agent.md) turn completes in
  **< 1 min**, first token well before that. It is a considered answer the user waits
  for, not an interaction, and the endpoint makes the wait legible with [progress
  events](/api/chat-endpoint.md) rather than trying to remove it. The budget is a
  ceiling on the whole turn: exceeding it means the loop is thrashing, and the levers
  are `chat_agent_max_iterations` and the two search knobs rather than a faster model.
- **NFR2:** Monthly cost under ~$30 at idle
- **NFR3:** Handles ~1000 docs, designed to scale to ~5000
- **NFR4:** Swedish language support end-to-end

## Constraints

- GCP, Python backend, React frontend
- Public domain source documents
- Budget-optimized

## Future Enhancements (V2)

- Mobile-optimized UI — only a 900px stacking breakpoint exists today; a
  designed-for-mobile layout is still out of scope

## Acceptance Criteria

- User can ask a Swedish legal question and receive a synthesized answer citing
  relevant decisions — **met**
- Agent correctly narrows retrieval using implicit filters from the query — **met**
- Ingestion pipeline processes full corpus with checkpointing, no duplicates on re-run
  — **met**
- System deployed and accessible via URL — **not met**; see [deployment
  state](/reference/deployment-state.md). No human has yet tested the complete system
  end-to-end either — that gap is deliberate and recorded, along with the checks that
  close it, in the [acceptance walkthrough](/playbooks/acceptance.md).
