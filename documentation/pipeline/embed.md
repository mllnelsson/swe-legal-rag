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
| `__main__.py` | Entry point — `subscribe()` builds the embedding provider, runs `ai.verify_embedding_dimension()` (see [embedding dimension](/decisions/embedding-dimension.md)) and `ai.verify_embedding_window()` (see [embedding window](/decisions/embedding-window.md)) before registering the handler, and passes the observed dimension and window into every `process_embedding()` call; `main()` calls `shared.worker.serve()`. |

## `process_embedding()`

`process_embedding(document_id, task_id, chunk_repo, task_repo, embedding_provider,
session, passage_prefix, expected_dimension, count_tokens, max_input_tokens)` defines a
`body()`:

1. Fetches all chunks via `chunk_repo.get_by_document_id(...)` — raises `NoChunksError`
   if empty (the chunk worker must run first).
2. Extracts embed texts: `passage_prefix + (chunk.contextual_text or chunk.chunk_text)`
   per chunk.
3. For each text, checks `count_tokens(text) + SPECIAL_TOKEN_COUNT` against
   `max_input_tokens` and logs a WARNING naming the chunk, document and token count for
   any that exceed it — see [input-length warning](#input-length-warning) below.
4. Calls `embedding_provider.embed(texts)` — a single batch call for all chunks. `local`
   (`sentence-transformers`, in-process) and `berget` (hosted) are both fully supported;
   which one runs is `embedding.provider` in
   [`llm_config.yaml`](/reference/llm-config.md) — see [embedding
   hosting](/decisions/embedding-hosting.md) for the trade-offs between them.
5. Validates: vector count matches chunk count (`EmbeddingCountMismatchError`); each
   vector is exactly `expected_dimension` (`EmbeddingDimensionError`).
6. Calls `chunk_repo.update_embeddings(session, [(chunk_id, vector), ...])` — a bulk
   UPDATE of the `embedding` column only.

### Input-length warning

`count_tokens` and `max_input_tokens` are both required, with no defaults — like
`expected_dimension`, they describe the model actually configured rather than a
process-wide constant nothing ties to it. An input longer than `max_input_tokens` is
**warned about and embedded anyway, untruncated** — never raised. The embedding model
truncates it silently regardless, so the warning is the only signal that a chunk's tail
never reached its vector, but one over-long chunk is degraded retrieval for that chunk
alone, whereas raising would fail the document's terminal step and have the message
redelivered forever. The [chunk worker](/pipeline/chunk.md) is where a chunk's length is
actually decided, via its own token budget — this check is what says out loud, at embed
time, whether that budget held.

`expected_dimension` is a required parameter, supplied by `__main__.py` from the width
`verify_embedding_dimension` actually observed the configured model producing — not read
back from `shared.config.EMBEDDING_DIMENSION` inside the service. `verify_embedding_dimension`
has already reconciled that constant with the resolved `EmbeddingConfig` at startup (see
[embedding dimension](/decisions/embedding-dimension.md)); this check validates each
batch against the provider that produced it.

`max_input_tokens` is supplied the same way, but from `ai.verify_embedding_window()`
rather than a declared constant: `__main__.py` builds an `ai.EmbeddingRuler`
(`ai.create_embedding_ruler()`) and calls
`verify_embedding_window(ruler, reserved_tokens=ruler.count_tokens(passage_prefix) +
SPECIAL_TOKEN_COUNT)`, logs `Embedding sequence window: <n> tokens`, and threads
`ruler.count_tokens` and the returned window into every `process_embedding()` call. The
dimension is declared in `llm_config.yaml` because the `chunks.embedding` column must
independently agree with it; the sequence window has no such counterpart, so — as with
the [chunk worker's](/pipeline/chunk.md) budget — it is read off the tokenizer instead of
declared anywhere. See [embedding window](/decisions/embedding-window.md) for the full
rationale; this is the principle's second instance in this codebase, after
`embedding.dimension` vs. the observed model width above.

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
