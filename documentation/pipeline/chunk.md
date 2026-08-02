---
type: Service
title: Chunk Worker
description: Subscriber worker that generates a document summary and splits body and appendices separately into overlapping token-bounded, section-labelled chunks with the summary prepended.
resource: packages/worker-chunk
tags: [pipeline, worker, chunk, contextual-retrieval]
timestamp: 2026-08-02T00:00:00Z
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
| `budget.py` | `ChunkBudget` (frozen pydantic model), `fixed_overhead_tokens()`, `compute_chunk_budget()` — derives the chunk/overlap/summary-reserve split from the embedding model's observed sequence window. |
| `errors.py` | `ChunkError`, `ChunkBudgetError` (raised when the window cannot fit the fixed overhead). |
| `chunker.py` | Pure functions: `split_into_chunks()` (sentence-aware, counted with the embedding model's own tokenizer), `split_document_into_chunks()` (segment-aware, returns `SectionedChunk`), `build_contextual_text()` and `truncate_summary()`. |
| `service.py` | `process_chunking()` async function — orchestration via functional DI. |
| `__main__.py` | Entry point — builds the embedding ruler, derives the chunk budget, verifies the window, wires dependencies, registers handler, calls `subscriber.start()`. |

## Chunking algorithm

`split_into_chunks(text, *, count_tokens, max_tokens, overlap_tokens)` — all three keyword-only,
none defaulted:

1. Returns `[]` for empty/whitespace-only text.
2. Splits into sentences by sentence-ending punctuation (`[.!?]` + whitespace) or blank
   lines (`\n{2,}`).
3. Greedily accumulates sentences until adding the next would exceed `max_tokens`.
4. When full: emits `" ".join(current_sentences)`, then rewinds — retains trailing
   sentences totalling ≤ `overlap_tokens` as the start of the next chunk.
5. A single sentence exceeding `max_tokens` is emitted as its own chunk with no overlap
   (`service.py` logs a WARNING when this fires — see below).

**Key decisions:**
- **Counted with the embedding model's own tokenizer**, not a general-purpose ruler.
  `count_tokens` has no default: it decides whether a chunk fits the embedding model's
  window, and a wrong ruler produces embeddings silently truncated at embed time. Callers
  pass `ai.create_embedding_ruler().count_tokens`. See [the embedding
  window decision](/decisions/embedding-window.md) for why this replaced a tiktoken-based
  budget and the arithmetic behind the numbers below.
- **The budget is derived, not hand-picked.** `worker_chunk.budget.compute_chunk_budget()`
  splits the embedding model's observed window (512 for e5-large) between the fixed
  overhead — `SPECIAL_TOKEN_COUNT` (2), the measured `passage_prefix` and separator token
  counts, `SUMMARY_RESERVE_TOKENS` (150) and `SAFETY_MARGIN_TOKENS` (8) — and the chunk
  text. At e5-large's window this lands on a **349-token chunk budget** and a **34-token
  overlap** (`OVERLAP_FRACTION`, 10% of the budget). A window too small for the fixed
  overhead raises `ChunkBudgetError` at startup rather than emitting empty chunks.
- **Sentence-aware** — never splits mid-sentence; Swedish legal text has clear `.`
  boundaries.
- **Overlap as a share of the budget**, not an absolute — it tracks the budget when the
  window or the summary reserve move.

`build_contextual_text(summary, chunk_text)` produces `"{summary}\n\n---\n\n{chunk_text}"`.
Only `contextual_text` is embedded, never shown to users; `chunk_text` remains the raw
text for citations (see [data model design notes](/data-model/design-notes.md)).

`truncate_summary(summary, *, count_tokens, max_tokens)` cuts a summary down to
`budget.summary_reserve_tokens` when it overruns: unchanged if it already fits, otherwise
cut on sentence boundaries, falling back to whole words for a run-on summary whose first
sentence alone overruns the reserve. The summary is prepended to every chunk, so an
over-long one does not overflow — it silently displaces chunk text from the window, which
is what this function exists to prevent.

## Segment scoping

`split_document_into_chunks(segments, *, count_tokens, budget)` chunks the body and **each appendix separately**,
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

`process_chunking(document_id, task_id, ..., count_tokens, budget, next_topic=EMBED,
llm_provider=None)` — `count_tokens` and `budget` are required, with no defaults; both
describe the embedding model's window, so a default here would silently budget against a
model unrelated to the one actually in use. Callers build them together with
`ai.create_embedding_ruler()` and `worker_chunk.budget.compute_chunk_budget()`.

`body()` around a summarize-role LLM provider
(`ai.providers.roles.create_summarize_llm_provider()`, Mistral Medium 3.5 via Berget by
default): validate the document → `split_document()` → `ai.summarize_document(body)` →
**truncate the summary once**, to `budget.summary_reserve_tokens`, via
`truncate_summary()` → store that one value via `DocumentUpdate` **and** prepend it to
every chunk, so `contextual_text.startswith(document.summary)` always holds →
`split_document_into_chunks(segments, count_tokens=count_tokens, budget=budget)` → delete
existing chunks (idempotency) → bulk insert `ChunkCreate` DTOs with `chunk_text`,
`contextual_text`, `section` and `appendix_label`. It hands `body` to the shared task
envelope with **`reraise=True`**, so unexpected work failures propagate for message
redelivery while a `StepInputError` is still swallowed (see [worker
patterns](/pipeline/worker-patterns.md)). Empty `raw_text` produces zero chunks — the
task still completes and publishes to embed.

Two WARNINGs signal the two ways a document can still overrun the window despite the
budget:

- **Summary truncated** — logged when `truncate_summary()` actually cuts the summary,
  naming the document, the original token count and the reserve. This is the signal that
  the summarization prompt's "högst 3 meningar och högst 60 ord" instruction is not
  holding for that document.
- **Chunk over budget** — logged per chunk whose `chunk_text` exceeds `budget.max_tokens`
  (the single-sentence-longer-than-the-budget path in `split_into_chunks`), naming the
  document, chunk index and token count. Its tail will be dropped when the embed worker
  embeds it.

## Startup invariant

`__main__.py`'s `subscribe()` builds the embedding ruler
(`ai.create_embedding_ruler()`), measures the `passage_prefix` and
`CONTEXTUAL_SEPARATOR` token counts with it, calls `ai.verify_embedding_window()`, and
derives the chunk budget from the returned window — all before the queue subscription
starts, so a window that cannot fit the fixed overhead is a refusal to start rather than
a stream of malformed chunks. It logs `Chunk budget: window=512 reserve=150 chunk=349
overlap=34` once. Warming the tokenizer here also means the first message is not charged
for loading it. See [the embedding window decision](/decisions/embedding-window.md).
