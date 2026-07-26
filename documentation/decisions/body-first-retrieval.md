---
type: Decision
title: Body-first retrieval over one vector index
description: Why appendix scoping is a WHERE predicate on the existing HNSW index rather than a second index, and why it must be a hard filter rather than a ranking penalty.
tags: [retrieval, pgvector, hnsw, chunking, appendix]
timestamp: 2026-07-26T00:00:00Z
---

# Body-first retrieval over one vector index

**Status:** Accepted

[chunks](/data-model/chunks.md) carries a `section` marker distinguishing the nämnd's own
text from the appealed decision (see
[appendices are labelled, not dropped](/decisions/appendix-segmentation.md)). This
decision covers how the [retrieval agent](/retrieval/agent.md) uses it.

## Decision

**One vector index, a `section` predicate, body-only by default, widen on empty.**

* `chunk_repo.vector_search` / `text_search` take `sections: Sequence[ChunkSection] | None`
  (`None` = no restriction).
* `RetrievalSettings.retrieval_include_appendices` (default `false`) is the deployment
  default; `DecomposeResult.include_appendices` lets the query planner widen per query.
* If body-only retrieval returns nothing, retrieval retries unrestricted and logs it.

## Why one index

Body and appendix chunks are the same kind of Swedish legal prose, embedded by the same
[e5-large model](/decisions/embedding-model.md) into the same 1024-dimension space, so
they are directly comparable. `section` is a filter, not a second embedding space.

The retriever already applies exactly this kind of predicate — `WHERE chunk.document_id
IN (:candidate_ids)` from the agent's entity/metadata pre-filter. A section predicate is
the same mechanism and considerably less selective.

The BM25 half needs nothing: GIN plus an equality predicate composes fine.

## Why a hard filter rather than a ranking penalty

The [embed worker](/pipeline/embed.md) embeds `contextual_text`, which is
`summary + "\n\n---\n\n" + chunk_text`. The summary is derived from the **body**. An
appendix chunk's embedding is therefore partly *about the nämnd's decision*, and will
score higher on body-shaped queries than its own text warrants.

Similarity cannot separate the two instances. The predicate has to be explicit.

## Deferred: the partial index

pgvector's HNSW index **post-filters** — the scan walks `hnsw.ef_search` candidates
(default 40) and applies the `WHERE` afterwards, so a selective filter can return fewer
rows than `limit`.

This is accepted for now. `section = 'body'` removes only ~25–50% of chunks, and the
same exposure already exists via `candidate_ids`. If measurement shows it biting, raise
`hnsw.ef_search` first; only then add a partial index:

```sql
CREATE INDEX ix_chunks_embedding_hnsw_body ON chunks
  USING hnsw (embedding vector_cosine_ops) WHERE section = 'body';
```

Postgres selects that automatically for a query carrying the matching predicate, so it
is a pure migration with no code change — the decision stays reversible, which is why it
is not being paid for upfront.

## Consequences

* The default answer draws only on Överklagandenämndens own reasoning, which is what
  [PRD](/prd.md) S6 ("citing specific decisions") means by a citation.
* Widening is agent-driven, consistent with "agent-driven filtering over user-driven" in
  the [architectural register](/decisions/architectural-register.md) and with PRD S3 (no
  manual filters in V1). No UI control is needed.
* The widen-on-empty retry costs one extra round-trip, and only on the empty path.
* `DocumentFilter` is unchanged — the predicate selects parts of a document, not
  documents, so it does not belong on the document-level pre-filter.
