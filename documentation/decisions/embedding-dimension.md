---
type: Decision
title: Embedding dimension coupling and startup verification
description: Why EMBEDDING_MODEL and EMBEDDING_DIMENSION must change together, and how a startup check guards the mismatch.
tags: [embedding, dimension, verification, hazard]
timestamp: 2026-07-24T00:00:00Z
---

# Embedding dimension coupling and startup verification

**Status:** Accepted

The [chunks.embedding](/data-model/chunks.md) column is `VECTOR(1024)` for
[`intfloat/multilingual-e5-large`](/decisions/embedding-model.md), configurable via
`EMBEDDING_DIMENSION` (default `1024`).

## The coupling

**`EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` must always change together**, plus a
migration recreating the `chunks.embedding` column at the new width. Vectors are not
portable across models: e5-base (768) and e5-large (1024) occupy different vector spaces,
so a model change invalidates every stored embedding and requires a full re-embed of the
corpus.

## Known hazard — the value lives in three places, nothing cross-checks them

| Location | When it is read |
|---|---|
| `shared/config.py` (`DEFAULT_EMBEDDING_DIMENSION`) | Python import time — configures the `Chunk` model |
| `alembic/versions/001_initial_schema.py` | `alembic upgrade` time — baked into the DDL |
| `ai/embedding.py` (`DEFAULT_EMBEDDING_MODEL`) | Implicitly, via the model's actual output width |

`EMBEDDING_DIMENSION` is read with a bare `os.environ.get` rather than a pydantic
setting, so nothing validates these against each other by construction. Setting
`EMBEDDING_MODEL` without setting `EMBEDDING_DIMENSION` is the most likely way to break
them apart.

## Guard — verify at startup, not per document

`ai.verify_embedding_dimension(provider)` embeds one throwaway string and compares the
observed width against `EMBEDDING_DIMENSION`, raising `EmbeddingDimensionMismatchError`
if they disagree. It runs in [worker-embed](/pipeline/embed.md)'s `__main__` before the
queue subscription starts, and in the [API](/packages/api.md)'s lifespan before it serves
traffic. Without it a mismatch surfaced only at the embed step as
`EmbeddingDimensionError` — after crawl, download, parse, metadata, extract and chunk had
already run.

The check is written against the `EmbeddingProvider` Protocol, not the local provider, so
a future HTTP-backed provider (such as the default [Berget-hosted
one](/decisions/embedding-hosting.md)) is covered unchanged. Because it performs a real
embed call, it also forces the local model to load eagerly.
