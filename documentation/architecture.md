---
type: Concept
title: Architecture Overview
description: The three-subsystem system architecture — ingestion pipeline, storage layer, and query/retrieval agent — and pointers to each area.
tags: [architecture, overview, system]
timestamp: 2026-08-05T00:00:00Z
---

# Architecture Overview

Three major subsystems, all running on GCP, scale-to-zero where possible:

1. **[Ingestion Pipeline](/pipeline/overview.md)** — a queue-driven, seven-step Cloud Run
   pipeline that crawls, downloads, parses, extracts metadata and entities, chunks, and
   embeds decisions.
2. **Storage Layer** — a single Postgres instance (see below) plus GCS for PDFs.
3. **[Query / Retrieval Agent](/retrieval/agent.md)** — decomposes the user's Swedish
   question, pre-filters, runs hybrid retrieval with RRF, optionally reranks, and
   synthesizes a cited answer.

The backend is a uv workspace of [packages](/packages/overview.md); the
[frontend](/frontend/overview.md) is a search UI over the deterministic
retrieval API — it does not call the [chat endpoint](/api/chat-endpoint.md).

## Storage layer

A single Postgres instance (Cloud SQL) with the pgvector extension serves four concerns
in one database:

- **Document registry** — ingestion state and metadata per document
  ([documents](/data-model/documents.md))
- **Chunk store** — [chunk](/data-model/chunks.md) text and positional info
- **Vector index** — pgvector `VECTOR(1024)` embeddings plus a GIN index on the tsvector
  column for Swedish full-text search
- **Entity graph** — [entities](/data-model/entities.md),
  [document_entities](/data-model/document-entities.md), and
  [document_references](/data-model/document-references.md); GraphRAG concepts as
  relational tables

PDFs live in a GCS bucket, served via signed URLs. The same bucket also holds the
append-only [LLM trace stream](/observability.md) — every prompt, response and token
count, written in batches as whole JSONL objects and deliberately kept out of Postgres
so the records stay cheap to write and easy to analyse offline. Cost is not stored; it
is derived from the model and tokens on read. **Why a single Postgres?** At ~1000
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
