---
type: Decision
title: Embedding model choice
description: Why intfloat/multilingual-e5-large (1024 dims) was selected for Swedish retrieval.
tags: [embedding, model, e5-large, swedish]
timestamp: 2026-08-02T00:00:00Z
---

# Embedding model choice

**Status:** Accepted — `intfloat/multilingual-e5-large` (1024 dimensions)

Chosen based on the [Scandinavian Embedding Benchmark
(SEB)](https://github.com/KennethEnevoldsen/Scandinavian-Embedding-Benchmark) results for
Swedish retrieval tasks. `e5-large` consistently outperforms `e5-base` and the
Swedish-specific `KBLab/sentence-bert-swedish-cased` on retrieval benchmarks.

| Model | Dims | Verdict |
|---|---|---|
| `intfloat/multilingual-e5-base` | 768 | Previous default. Weaker Swedish retrieval quality. |
| `intfloat/multilingual-e5-large` | 1024 | **Selected.** Best balance of Swedish quality, open-source, and sentence-transformers compatibility. |
| `BAAI/bge-m3` | 1024 | Top multilingual benchmark performer. Heavier, more complex (dense+sparse+ColBERT). Not needed at this scale. |
| `KBLab/sentence-bert-swedish-cased` | 768 | Swedish-specific (National Library of Sweden). Strong but less actively maintained; SEB shows e5-large edges it on retrieval. |
| Google `text-embedding-004` | 768 | Managed API, cheapest to run. Proprietary — locks model choice to Google, no local dev parity. |

The model is used at **both** ingestion and query time via the `EmbeddingProvider`
abstraction; ingestion and query embeddings must come from the same model or the vector
spaces are incompatible. Where the model is hosted is a separate decision — see
[embedding hosting](/decisions/embedding-hosting.md) — and the width coupling and its
startup guard are in [embedding dimension](/decisions/embedding-dimension.md).

## Token counting for chunking

The [chunk worker](/pipeline/chunk.md) measures chunk sizes with **the embedding model's
own tokenizer** (`transformers.AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")`),
not a general-purpose ruler. What decides whether a chunk survives embedding intact is
e5's tokenizer, so that is the only honest way to measure against it — see [the embedding
window decision](/decisions/embedding-window.md) for the budget this produces and why the
window itself is observed rather than declared.

This replaced an earlier design that measured chunks in tiktoken `cl100k_base` (GPT-4's
tokenizer) against a hand-picked ~500-token budget. That was backwards on two counts: it
answered a question about a different tokenizer, and it undercounted the risk rather than
overcounting it. Measured on real Swedish decision text, cl100k runs **~1.37×** the e5
(XLM-R) tokenizer — a 500-cl100k-token chunk is only ~365 e5 tokens — so a budget kept in
cl100k tokens was not conservative, it was simply unrelated to the limit that decides
truncation. Passages built from it measured as high as 520 e5 tokens against e5's
512-token window, with the excess silently dropped from the vector by
`sentence-transformers` at embed time.
