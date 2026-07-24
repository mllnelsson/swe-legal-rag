---
type: Decision
title: Embedding model choice
description: Why intfloat/multilingual-e5-large (1024 dims) was selected for Swedish retrieval, and the tiktoken tokenizer used for chunk sizing.
tags: [embedding, model, e5-large, swedish]
timestamp: 2026-07-24T00:00:00Z
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

The [chunk worker](/pipeline/chunk.md) uses **tiktoken `cl100k_base`** to measure chunk
sizes in tokens. This is a token-counting ruler, not the embedding model — it decides
where to split, not how to embed. `cl100k_base` (GPT-4's tokenizer) does not match the e5
WordPiece tokenizer and tends to undercount tokens for Swedish text, so the ~500-token
chunk budget includes headroom to keep chunks within e5's 512-token max sequence length.
