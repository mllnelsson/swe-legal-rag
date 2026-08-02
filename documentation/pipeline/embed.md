---
type: Service
title: Embed Worker
description: Terminal pipeline worker that generates vector embeddings for a document's chunks and bulk-updates the chunks table.
resource: packages/worker-embed
tags: [pipeline, worker, embed, vector, terminal]
timestamp: 2026-08-02T00:00:00Z
---

# Embed Worker (`packages/worker-embed/`)

Long-running subscriber and **terminal pipeline step**. Consumes embed tasks, generates
vector embeddings for all [chunks](/data-model/chunks.md) of a document, and performs a
bulk UPDATE on the chunks table (no downstream publish).

## Module layout

| Module | Role |
|---|---|
| `config.py` | `EmbedSettings(BaseSettings)` — `EMBED_TOPIC` (`PipelineStep.EMBED`). `get_embed_settings()` is `@lru_cache`. |
| `service.py` | `process_embedding()` async function — orchestration via functional DI. |
| `__main__.py` | Entry point — `subscribe()` builds the embedding provider, runs `ai.verify_embedding_dimension()` before registering the handler (see [embedding dimension](/decisions/embedding-dimension.md)), and passes the observed dimension into every `process_embedding()` call; `main()` calls `shared.worker.serve()`. |

## `process_embedding()`

`process_embedding(document_id, task_id, chunk_repo, task_repo, embedding_provider,
session, passage_prefix, expected_dimension)` defines a `body()`:

1. Fetches all chunks via `chunk_repo.get_by_document_id(...)` — raises `NoChunksError`
   if empty (the chunk worker must run first).
2. Extracts embed texts: `passage_prefix + (chunk.contextual_text or chunk.chunk_text)`
   per chunk.
3. Calls `embedding_provider.embed(texts)` — a single batch call for all chunks. The
   default provider is [Berget-hosted](/decisions/embedding-hosting.md); `local`
   (`sentence-transformers`) remains available.
4. Validates: vector count matches chunk count (`EmbeddingCountMismatchError`); each
   vector is exactly `expected_dimension` (`EmbeddingDimensionError`).
5. Calls `chunk_repo.update_embeddings(session, [(chunk_id, vector), ...])` — a bulk
   UPDATE of the `embedding` column only.

`expected_dimension` is a required parameter, supplied by `__main__.py` from the width
`verify_embedding_dimension` actually observed the configured model producing — not read
back from `shared.config.EMBEDDING_DIMENSION` inside the service. `verify_embedding_dimension`
has already reconciled that constant with the resolved `EmbeddingConfig` at startup (see
[embedding dimension](/decisions/embedding-dimension.md)); this check validates each
batch against the provider that produced it.

## The passage prefix

`passage_prefix` is the document side of the embedding model's asymmetric prefix pair.
It comes from `embedding.passage_prefix` in
[`llm_config.yaml`](/reference/llm-config.md), read by `ai.get_embedding_prefixes()` in
`__main__.py` and threaded in — the same call the
[retrieval agent](/retrieval/agent.md) uses for the query half, so the two cannot drift
apart.

**The parameter has no default, deliberately.** e5 is trained with `"query: "` on one
side and `"passage: "` on the other, and prefixing only one side is worse than prefixing
neither: queries and passages land in systematically offset regions of the space. That
is precisely the bug this parameter replaced — the query side was prefixed, the passage
side never was, and a comment in the retriever asserted otherwise. A forgotten default
would reintroduce it silently. Pass `""` for a model that uses no prefixes.

Changing either prefix changes what gets embedded, so it **invalidates every stored
vector** — see the re-embed step in [live testing](/playbooks/live-testing.md).

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
