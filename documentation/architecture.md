---
type: Concept
title: Architecture Overview
description: The three-subsystem system architecture — ingestion pipeline, storage layer, and the conversational agent — plus the three ways to query the corpus and pointers into each area.
tags: [architecture, overview, system]
timestamp: 2026-08-14T00:00:00Z
---

# Architecture Overview

Three major subsystems, all running on GCP, scale-to-zero where possible:

1. **[Ingestion Pipeline](/pipeline/overview.md)** — a queue-driven, seven-step Cloud Run
   pipeline that crawls, downloads, parses, extracts metadata and entities, chunks, and
   embeds decisions.
2. **Storage Layer** — a single Postgres instance (see below) plus GCS for PDFs.
3. **[Conversational Agent](/retrieval/chat-agent.md)** — drives the deterministic
   retrieval tool set and two sub-agents in a tool loop, then synthesizes a cited
   Swedish answer over an SSE stream.

The backend is a uv workspace of [packages](/packages/overview.md); the
[frontend](/frontend/overview.md) has a surface for each of the first two — a
search UI over the deterministic retrieval API, and agent mode, an SSE client
for the [chat endpoint](/api/chat-endpoint.md) with a rail of past conversations
over [`/api/sessions`](/api/sessions.md).

## Three ways to query the corpus

- **[Deterministic search](/retrieval/deterministic-search.md)** (`/api/search`) — hybrid
  vector + full-text retrieval, no LLM unless expansion is requested. Finds passages;
  the frontend's search surface.
- **[The conversational agent](/retrieval/chat-agent.md)** (`/api/chat`) — a tool loop
  over the two paths below plus a document reader, ending in a cited
  natural-language answer streamed over SSE. It reimplements neither: its search tool
  wraps `/api/search` and its counting tool is the SQL agent, so it inherits both of
  their guarantees rather than restating them.
- **[The SQL agent](/packages/agents.md)** (`/api/sql`) — answers what neither of the above
  can: counting and aggregate questions over the corpus's structured metadata. An LLM tool
  loop converts a Swedish question to a read-only SQL query, grounding any predicate over
  a free-text column against the values that actually exist before running it (see [the
  grounding decision](/decisions/sql-agent.md)), and returns the query and its rows — never
  an interpreted answer. See [the endpoint contract](/api/sql-agent.md).

## Storage layer

A single Postgres instance (Cloud SQL) with the pgvector extension serves five concerns
in one database:

- **Document registry** — ingestion state and metadata per document
  ([documents](/data-model/documents.md))
- **Chunk store** — [chunk](/data-model/chunks.md) text and positional info
- **Vector index** — pgvector `VECTOR(1024)` embeddings plus a GIN index on the tsvector
  column for Swedish full-text search
- **Conversation history** — [sessions](/data-model/sessions.md), the only table
  anything here writes or deletes; read back by [`/api/sessions`](/api/sessions.md)
- **Entity graph** — [entities](/data-model/entities.md),
  [document_entities](/data-model/document-entities.md), and
  [document_references](/data-model/document-references.md); GraphRAG concepts as
  relational tables

PDFs live in a GCS bucket, served via signed URLs. [LLM traces](/observability.md) —
every prompt, response and token count — are local files instead, one per billed call,
deliberately kept out of Postgres so the records stay cheap to write and easy to
analyse offline. Cost is not stored; it is derived from the model and tokens on read.
**Why a single Postgres?** At ~1000
docs this is not a scale problem — pgvector handles it trivially, and hybrid search
(vector + full text + structured SQL filters) happens in one query with no separate
vector DB (see the [architectural register](/decisions/architectural-register.md)).

## Infrastructure and cost

The GCP service layout and its local-dev equivalents are in the
[GCP layout](/reference/gcp-layout.md) reference; the idle/low-usage cost breakdown is in
the [cost estimate](/reference/cost-estimate.md).

## Key decisions

The consolidated architectural decision record is the
[architectural register](/decisions/architectural-register.md); the embedding-specific
decisions have their own records —
[embedding model](/decisions/embedding-model.md),
[embedding hosting](/decisions/embedding-hosting.md), and
[embedding dimension](/decisions/embedding-dimension.md).
