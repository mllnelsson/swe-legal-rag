---
type: Service
title: Chunk Worker
description: Subscriber worker that generates a document summary and splits body and appendices separately into overlapping token-bounded, section-labelled chunks with the summary prepended.
resource: packages/worker-chunk
tags: [pipeline, worker, chunk, contextual-retrieval]
timestamp: 2026-07-26T00:00:00Z
---

# Chunk Worker (`packages/worker-chunk/`)

Long-running subscriber. Consumes chunk tasks, segments
[`documents.raw_text`](/data-model/documents.md) via
[`shared.segmentation`](/reference/document-structure.md), generates a document-level
summary via LLM, splits the body and each appendix into overlapping token-bounded chunks
with the summary prepended (contextual retrieval), stores them in
[chunks](/data-model/chunks.md), and enqueues embed tasks.

## Module layout

| Module | Role |
|---|---|
| `config.py` | `ChunkSettings(BaseSettings)` — `CHUNK_TOPIC` (`chunk`), `CHUNK_NEXT_TOPIC` (`embed`). `get_chunk_settings()` is `@lru_cache`. |
| `chunker.py` | Pure functions: `split_into_chunks()` (sentence-aware, tiktoken-based), `split_document_into_chunks()` (segment-aware, returns `SectionedChunk`) and `build_contextual_text()`. |
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

## Segment scoping

`split_document_into_chunks(segments)` chunks the body and **each appendix separately**,
returning `SectionedChunk(text, section, appendix_label)`. Body chunks come first, then
appendices in order; `chunk_index` is a single monotonic sequence over the whole
document.

- **No chunk straddles the body/appendix boundary.** A chunk holding both the nämnd's
  reasoning and the decision it was reviewing could not be honestly labelled as either.
- **The trailer is not chunked at all.** `Sökord` / `Ärendenummer` / `Beslut` are already
  structured columns on [documents](/data-model/documents.md), and indexing them only
  adds noise to the Swedish `tsvector`.
- **The summary is generated from `segments.body` only.** It is prepended to every
  chunk's `contextual_text` — including appendix chunks — so a summary derived from the
  whole document would leak the appealed decision into every embedding for that document.
  This is also why retrieval cannot separate the two instances by similarity alone; see
  [body-first retrieval](/decisions/body-first-retrieval.md).

## Service layer

`process_chunking(...)` builds a `body()` around a summarize-role LLM provider
(`ai.providers.roles.create_summarize_llm_provider()`, Mistral Medium 3.5 via Berget by
default): validate the document → `split_document()` → `ai.summarize_document(body)` →
store the summary → `split_document_into_chunks()` → delete existing chunks (idempotency)
→ bulk insert `ChunkCreate` DTOs with `chunk_text`, `contextual_text`, `section` and
`appendix_label`. It hands `body` to the shared task envelope with
**`reraise=True`**, so unexpected work failures propagate for message redelivery while a
`StepInputError` is still swallowed (see [worker patterns](/pipeline/worker-patterns.md)).
Empty `raw_text` produces zero chunks — the task still completes and publishes to embed.
