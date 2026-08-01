---
type: Decision
title: Embedding dimension coupling and startup verification
description: Why EMBEDDING_MODEL and EMBEDDING_DIMENSION must change together, and how a startup check guards the mismatch.
tags: [embedding, dimension, verification, hazard]
timestamp: 2026-08-01T00:00:00Z
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

## The value lives in four places

| Location | When it is read | Cross-checked at startup |
|---|---|---|
| `llm_config.yaml` (`embedding.dimension`) | Process start, by [`ai.llm_config`](/reference/llm-config.md) | Yes |
| `shared/config.py` (`EMBEDDING_DIMENSION`) | Python import time — configures the `Chunk` model | Yes |
| `ai/llm_config.py` (`embedding.model`) | Implicitly, via the model's actual output width | Yes |
| `alembic/versions/001_initial_schema.py` | `alembic upgrade` time — baked into the DDL | **No** |

`EMBEDDING_DIMENSION` is read with a bare `os.environ.get` rather than a pydantic
setting, so nothing validates these against each other *by construction*. Setting
`EMBEDDING_MODEL` without setting `EMBEDDING_DIMENSION` is the most likely way to break
them apart.

**This used to be an unguarded hazard across three locations; three of the four are now
compared at startup** by the guard below. The migration's DDL remains outside the check —
nothing reads the live column width — so recreating `chunks.embedding` is still a manual
step that must accompany any change.

## Guard — verify at startup, not per document

`ai.verify_embedding_dimension(provider, config=None)` compares **three** values:
`embedding.dimension` from `llm_config.yaml`, `shared.config.EMBEDDING_DIMENSION`, and
the width the model actually produces for one throwaway probe string. Any disagreement
raises `EmbeddingDimensionMismatchError` naming which two disagree. The
configured-vs-configured comparison happens *before* the probe, so a mismatch between the
two declarations costs nothing to detect. It runs in
[worker-embed](/pipeline/embed.md)'s `__main__` before the
queue subscription starts, and in the [API](/packages/api.md)'s lifespan before it serves
traffic. Without it a mismatch surfaced only at the embed step as
`EmbeddingDimensionError` — after crawl, download, parse, metadata, extract and chunk had
already run.

The check is written against the `EmbeddingProvider` Protocol, not the local provider, so
a future HTTP-backed provider (such as the default [Berget-hosted
one](/decisions/embedding-hosting.md)) is covered unchanged. Because it performs a real
embed call, it also forces the local model to load eagerly.
