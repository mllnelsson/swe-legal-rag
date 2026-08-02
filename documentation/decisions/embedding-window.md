---
type: Decision
title: Embedding sequence window is observed, not declared
description: Why the chunk token budget is derived from the embedding model's own tokenizer and its observed sequence window rather than a hand-picked constant, and the arithmetic behind the 349-token chunk budget.
tags: [embedding, tokenization, chunking, window, e5-large]
timestamp: 2026-08-02T00:00:00Z
---

# Embedding sequence window is observed, not declared

**Status:** Accepted

## The bug this closes

What actually gets embedded per chunk is

```
"passage: " + summary + "\n\n---\n\n" + chunk_text
```

`intfloat/multilingual-e5-large` has a 512-token window and `sentence-transformers`
truncates silently past it — no error, no log line, just a vector built from a truncated
input. Measured on two real decisions with the real e5 tokenizer, passages came out at
[479, 318] and [506, 492, **520**, 278] tokens: one already over the window, most of the
rest sitting on the ceiling.

Two things fed it. First, the [chunk worker](/pipeline/chunk.md) budgeted 500 tokens
in tiktoken `cl100k_base` while the model counts in its own (XLM-R) tokenizer — see
[embedding model choice](/decisions/embedding-model.md) for the measured 1.37× gap
between them on Swedish text. Second, the document summary prepended to every chunk was
unbounded: the prompt asked for "2–4 meningar," the `summarize` role set no `max_tokens`,
and nothing in code capped the result. The summary, not the chunk text, was what blew the
window.

## Decision

Budget chunks with the embedding model's own tokenizer, and treat the model's sequence
window as **observed at process startup**, never declared as a constant anywhere in
config or code.

`packages/ai/src/ai/tokenization.py` provides the ruler:

- `EmbeddingRuler` — a frozen dataclass carrying `count_tokens` (a plain
  `Callable[[str], int]`) and `max_sequence_tokens`.
- `create_embedding_ruler(config=None)` loads `AutoTokenizer.from_pretrained(model)`
  (`@lru_cache`d, since `scripts/run_pipeline.py` composes the chunk and embed workers
  into one process) and reads `tokenizer.model_max_length` as the window.
- `verify_embedding_window(ruler, *, reserved_tokens)` is the startup guard — see below.

`count_tokens` returns **content tokens only** (`add_special_tokens=False`); a caller
composing several pieces into one input adds `SPECIAL_TOKEN_COUNT` (2, the `<s>`/`</s>`
an XLM-R-style tokenizer wraps around the whole encoded input) once for the assembled
string, not once per piece.

## Why observed, not declared

`embedding.dimension` **is** declared in `llm_config.yaml`, and deliberately so: a second
artefact, the `chunks.embedding` column, has to independently agree with it, and nothing
else can reconcile the two — see [embedding dimension](/decisions/embedding-dimension.md).
The sequence window has no such counterpart. Nothing outside the process is constrained
by it, so a declared copy could only ever drift out of step with the tokenizer that
actually enforces it. `llm_config.yaml` carries a comment recording this next to
`embedding:` rather than a `max_sequence_tokens` key.

**The sentinel guard.** `transformers` reports `model_max_length` as `int(1e30)` when a
tokenizer's config omits the field. Reading that unguarded turns into an unbounded chunk
budget — the exact bug this decision closes, returning in a different shape. Any window
observed at or above `MODEL_MAX_LENGTH_SENTINEL_FLOOR = 1_000_000` is treated as
unobservable and raises `EmbeddingWindowError` at startup instead of being trusted as a
number.

## The budget arithmetic

What worker-embed actually sends the model is `passage_prefix + summary + separator +
chunk_text`, wrapped in the tokenizer's special tokens. Every one of those pieces spends
the same window, so `packages/worker-chunk/src/worker_chunk/budget.py` derives the chunk
text's share as the window minus everything else:

```
window                                    512
special tokens                              2   SPECIAL_TOKEN_COUNT
"passage: "                                 2   measured, not assumed
summary reserve                           150   SUMMARY_RESERVE_TOKENS
"\n\n---\n\n"                                1   measured, not assumed
safety margin                               8   SAFETY_MARGIN_TOKENS
                                         ----
chunk budget                              349
overlap                                    34   OVERLAP_FRACTION (10%) of the budget
```

The prefix and separator token counts are **measured at startup with the real ruler**,
not hard-coded — `passage_prefix` is configuration (`""` for a model with no prefixes)
and the separator is a chunker constant, so a hard-coded 2 and 1 would mis-budget the
moment either moves.

`SUMMARY_RESERVE_TOKENS = 150` is sized against the two summaries measured on real
decisions (110 and 143 content tokens), so a compliant summary clears it untouched — truncation
is a backstop for a model that ignores its instructions, not routine mutilation of
well-behaved output. The [summarization prompt](/packages/ai.md) now asks for "högst 3
meningar och högst 60 ord" (measured at 2.0–2.24 e5 tokens/word, so 60 words lands at
120–135 tokens, inside the reserve), and the `summarize` role sets `max_tokens: 256` as a
coarse stop on runaway generation. `worker_chunk.chunker.truncate_summary()` is the
enforced ceiling — cutting on sentence boundaries, falling back to whole words — because
a provider-side cut lands mid-word.

`SAFETY_MARGIN_TOKENS = 8` absorbs the difference between counting pieces separately and
encoding them as one string; the measured inputs agree exactly, so the margin exists for
a tokenizer that merges tokens across a piece boundary.

## Where the guard runs

`verify_embedding_window` runs once, at startup, in every process that chunks or embeds:
worker-chunk's `__main__.py` (deriving the chunk budget from the returned window),
worker-embed's `__main__.py` (deriving `max_input_tokens` from
`passage_prefix` tokens + `SPECIAL_TOKEN_COUNT`), and both `CHUNK`/`EMBED` cases in
`scripts/run_step.py`, so a hand-tested run budgets against the same numbers the workers
would use. It fails before the queue subscription starts and warms the tokenizer, so the
first message is not charged for loading it — mirroring
[`verify_embedding_dimension`](/decisions/embedding-dimension.md).

A chunk that still overruns the budget (a single sentence longer than 349 tokens, emitted
whole rather than cut mid-thought) and any input the embed worker sees over the window
are not fatal — see [chunk worker](/pipeline/chunk.md) and
[embed worker](/pipeline/embed.md) for the two warnings this produces.

## Consequence: worker-chunk needs the tokenizer at startup

`AutoTokenizer.from_pretrained` contacts the HuggingFace hub unless the tokenizer files
are already cached. worker-chunk did not need this before; it now fails to start without
either hub access or a warm cache — see [local dev](/playbooks/local-dev.md).

## The escape hatch: `EMBEDDING_WINDOW_OVERRIDE`

A process that can reach neither the hub nor a warm cache sets
`EMBEDDING_WINDOW_OVERRIDE` in its environment. The window becomes that number, **no
tokenizer is loaded**, and `count_tokens` falls back to
`ceil(len(text) / ESTIMATED_CHARS_PER_TOKEN)`.

It is environment-only, and absent from `embedding:` in `llm_config.yaml` by the same
argument as above: one machine opting out is not the file declaring a second source of
truth for every machine. Whoever sets it owns the number being right for the model — the
startup log line says so, at WARNING.

`ESTIMATED_CHARS_PER_TOKEN = 2.0` is the **densest** Swedish text measured on real
decisions (0.5 tokens per character), not the average (~0.29, i.e. ~3.5 chars/token). A
worst-case constant is the point: the estimate can then only run high, so the failure it
can cause is chunks smaller than they needed to be, never a chunk that overruns the
window. Verified end to end on the two traced decisions — the exact ruler produces 6
chunks with a worst passage of 475/512 tokens; the estimate produces 12 chunks with a
worst passage of 257/512. **Roughly double the chunks, at half the context each**, which
is the standing price of not having the real tokenizer. It is a way to run, not a way to
run well.

`verify_embedding_window` still applies to the overridden value: it is checked for being
positive and for leaving room after the fixed overhead. Only the sentinel check is moot,
since an operator-supplied number is never `int(1e30)`.
