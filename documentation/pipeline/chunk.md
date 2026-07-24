---
type: Service
title: Chunk Worker
description: Subscriber worker that generates a document summary and splits text into overlapping token-bounded chunks with the summary prepended (contextual retrieval).
resource: packages/worker-chunk
tags: [pipeline, worker, chunk, contextual-retrieval]
timestamp: 2026-07-24T00:00:00Z
---

# Chunk Worker (`packages/worker-chunk/`)

Long-running subscriber. Consumes chunk tasks, generates a document-level summary via
LLM, splits [`documents.raw_text`](/data-model/documents.md) into overlapping
token-bounded chunks with the summary prepended (contextual retrieval), stores them in
[chunks](/data-model/chunks.md), and enqueues embed tasks.

## Module layout

| Module | Role |
|---|---|
| `config.py` | `ChunkSettings(BaseSettings)` — `CHUNK_TOPIC` (`chunk`), `CHUNK_NEXT_TOPIC` (`embed`). `get_chunk_settings()` is `@lru_cache`. |
| `chunker.py` | Pure functions: `split_into_chunks()` (sentence-aware, tiktoken-based) and `build_contextual_text()`. |
| `service.py` | `process_chunking()` async function — orchestration via functional DI. |
| `__main__.py` | Entry point — wires dependencies, registers handler, calls `subscriber.start()`. |

## Chunking algorithm

`split_into_chunks(text, max_tokens=500, overlap_tokens=50, encoding_name="cl100k_base")`:

1. Returns `[]` for empty/whitespace-only text.
2. Splits into sentences by sentence-ending punctuation (`[.!?]` + whitespace) or blank
   lines (`\n{2,}`).
3. Greedily accumulates sentences until adding the next would exceed `max_tokens`.
4. When full: emits `" ".join(current_sentences)`, then rewinds — retains trailing
   sentences totalling ≤ `overlap_tokens` as the start of the next chunk.
5. A single sentence exceeding `max_tokens` is emitted as its own chunk with no overlap.

**Key decisions:**
- **tiktoken `cl100k_base`** is used purely as a token-counting ruler, not the embedding
  model. It undercounts relative to the e5 WordPiece tokenizer for Swedish, so the ~500
  token budget leaves headroom to stay within e5's 512-token max sequence length — see
  the [embedding model](/decisions/embedding-model.md) decision.
- **Sentence-aware** — never splits mid-sentence; Swedish legal text has clear `.`
  boundaries.
- **50-token overlap** — the last sentences of the previous chunk repeat at the start of
  the next, preserving cross-boundary context for embedding.

`build_contextual_text(summary, chunk_text)` produces `"{summary}\n\n---\n\n{chunk_text}"`.
Only `contextual_text` is embedded, never shown to users; `chunk_text` remains the raw
text for citations (see [data model design notes](/data-model/design-notes.md)).

## Service layer

`process_chunking(...)` builds a `body()` around a summarize-role LLM provider
(`ai.providers.roles.create_summarize_llm_provider()`, Mistral Medium 3.5 via Berget by
default): validate the document → `ai.summarize_document()` → store the summary → split
into chunks → delete existing chunks (idempotency) → bulk insert `ChunkCreate` DTOs with
both `chunk_text` and `contextual_text`. It hands `body` to the shared task envelope with
**`reraise=True`**, so unexpected work failures propagate for message redelivery while a
`StepInputError` is still swallowed (see [worker patterns](/pipeline/worker-patterns.md)).
Empty `raw_text` produces zero chunks — the task still completes and publishes to embed.
