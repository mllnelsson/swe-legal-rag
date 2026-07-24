---
type: Service
title: Embed Worker
description: Terminal pipeline worker that generates vector embeddings for a document's chunks and bulk-updates the chunks table.
resource: packages/worker-embed
tags: [pipeline, worker, embed, vector, terminal]
timestamp: 2026-07-24T00:00:00Z
---

# Embed Worker (`packages/worker-embed/`)

Long-running subscriber and **terminal pipeline step**. Consumes embed tasks, generates
vector embeddings for all [chunks](/data-model/chunks.md) of a document, and performs a
bulk UPDATE on the chunks table (no downstream publish).

## Module layout

| Module | Role |
|---|---|
| `config.py` | `EmbedSettings(BaseSettings)` — `EMBED_TOPIC` (`embed`). `get_embed_settings()` is `@lru_cache`. |
| `service.py` | `process_embedding()` async function — orchestration via functional DI. |
| `__main__.py` | Entry point — wires dependencies, registers handler, calls `subscriber.start()`. Runs `ai.verify_embedding_dimension()` before subscribing (see [embedding dimension](/decisions/embedding-dimension.md)). |

## `process_embedding()`

`process_embedding(document_id, task_id, chunk_repo, task_repo, embedding_provider,
session)` defines a `body()`:

1. Fetches all chunks via `chunk_repo.get_by_document_id(...)` — raises `NoChunksError`
   if empty (the chunk worker must run first).
2. Extracts embed texts: `chunk.contextual_text or chunk.chunk_text` per chunk.
3. Calls `embedding_provider.embed(texts)` — a single batch call for all chunks. The
   default provider is [Berget-hosted](/decisions/embedding-hosting.md); `local`
   (`sentence-transformers`) remains available. Passages are embedded with e5's
   `"passage: "` convention (symmetric with the `"query: "` prefix the
   [retrieval agent](/retrieval/agent.md) uses).
4. Validates: vector count matches chunk count (`EmbeddingCountMismatchError`); each
   vector is exactly `EMBEDDING_DIMENSION` (`EmbeddingDimensionError`).
5. Calls `chunk_repo.update_embeddings(session, [(chunk_id, vector), ...])` — a bulk
   UPDATE of the `embedding` column only.

It hands `body` to the shared task envelope with `next_step=None` (terminal — no
publisher, no downstream task) and `reraise=True` (failures re-raise for redelivery). The
`EmbeddingError` subtypes are regular exceptions, not `StepInputError`, so they re-raise.

## Notes

- **Batch embedding:** all chunks for a document in one `embed()` call — efficient for
  the 10–50 chunks of a typical legal document.
- **`tsv` is GENERATED ALWAYS:** the `chunks.tsv` column is populated by PostgreSQL at
  chunk INSERT time from `chunk_text`; the embed worker never touches it — an UPDATE of a
  `GENERATED ALWAYS STORED` column errors (see
  [data model design notes](/data-model/design-notes.md)).
- **Idempotency:** UPDATE semantics overwrite embeddings; no duplicate chunks are
  created.
