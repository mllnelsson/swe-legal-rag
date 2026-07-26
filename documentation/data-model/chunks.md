---
type: Table
title: chunks
description: The retrieval unit — chunk text, the contextual text that is embedded, the vector, the Swedish full-text vector, and which part of the source PDF it came from.
resource: postgres://chunks
tags: [data-model, table, chunks, retrieval, embedding]
timestamp: 2026-07-26T00:00:00Z
---

# `chunks`

The retrieval layer. Each chunk is a unit of search and retrieval.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| document_id | UUID | FK → [documents](/data-model/documents.md) |
| chunk_index | INTEGER | Position within document (ordering) |
| chunk_text | TEXT | Raw chunk content. Displayed in citations. |
| contextual_text | TEXT | Summary + chunk text. Used for embedding. Never shown to end users. |
| section | VARCHAR | `body` \| `appendix` — which part of the source PDF this came from. NOT NULL, defaults to `body`. |
| appendix_label | VARCHAR | Nullable. The `Bilaga A` label, when `section` is `appendix`. |
| embedding | VECTOR(1024) | pgvector. Width is set by the embedding model — see [embedding dimension](/decisions/embedding-dimension.md) |
| tsv | TSVECTOR | Generated from `chunk_text` using the Swedish text search config. For BM25-style search. |
| created_at | TIMESTAMPTZ | Row creation |

`chunk_text` is what the user sees in citations; `contextual_text` (the document summary
prepended to the chunk) is what gets embedded and searched against, and is never shown
to end users.

`section` records provenance. A decision PDF carries the decision that was appealed as a
`Bilaga X` appendix, so an `appendix` chunk holds the **lower instance's** words — often
the reasoning Överklagandenämnden went on to overturn. Retrieval defaults to `body`
chunks and citations carry the marker through to the wire; see
[body-first retrieval](/decisions/body-first-retrieval.md) and
[decision document structure](/reference/document-structure.md). The `body` default is
what keeps chunks written before segmentation behaving as they did; re-chunking replaces
them, since chunking is DELETE+INSERT. `tsv` is a `GENERATED ALWAYS ... STORED` column populated automatically at
insert time — see [design notes](/data-model/design-notes.md). Chunks are produced by
the [chunk worker](/pipeline/chunk.md) and vectors written by the
[embed worker](/pipeline/embed.md). Retrieval over this table is described in the
[retrieval agent](/retrieval/agent.md).
