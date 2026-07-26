---
type: Decision
title: Appendices are labelled, not dropped
description: Why appended lower-instance decisions stay in the index with a section marker rather than being discarded or left undistinguished.
tags: [segmentation, appendix, bilaga, chunking, extraction]
timestamp: 2026-07-26T00:00:00Z
---

# Appendices are labelled, not dropped

**Status:** Accepted

Decision PDFs carry the appealed decision as a `Bilaga X` appendix — see
[decision document structure](/reference/document-structure.md). Once
`shared.segmentation` can tell body from appendix, three options existed for what to do
with the appendix text.

## Decision

**Keep appendix content in the index, marked with its provenance.**
[chunks](/data-model/chunks.md) gains `section` (`body` | `appendix`) and
`appendix_label`, and the marker travels all the way to the citation on the wire
(see the [chat endpoint](/api/chat-endpoint.md)).

## Why not the alternatives

**Drop appendices entirely** (body-only for chunking as well as extraction) is cheaper
and needs no migration, but it removes the facts of the underlying case from the corpus.
"Vad beslutade stiftet?" is a question the users of a legal research tool will ask, and
the answer exists only in the appendix.

**Leave them undistinguished** is what the system did before, and it is the failure this
work exists to fix: the lower instance's reasoning — often the reasoning the nämnd
overturned — was retrievable and citable as the nämnd's own.

## Consequences

* A migration is required (`004`). `chunks.section` is `NOT NULL DEFAULT 'body'` so
  pre-existing chunks, cut from unsegmented text, keep today's retrieval behaviour until
  the document is re-chunked. Re-chunking is DELETE+INSERT, so a re-run replaces them.
* The [chunk worker](/pipeline/chunk.md) chunks body and each appendix **separately**.
  A chunk straddling the boundary could not be honestly labelled as either.
* The **trailer is not chunked.** Its content (`Sökord`, `Ärendenummer`, `Beslut`) is
  already structured on [documents](/data-model/documents.md), and indexing it only adds
  noise to the Swedish `tsvector`.
* The document summary is generated from the **body only**. It is prepended to every
  chunk's `contextual_text`, so an appendix-derived summary would leak the appealed
  decision into every embedding for that document.
* Entity relevance is no longer positional. The old rule promoted anything past 60% of
  the text to `primary`, which an appendix inverts — the tail of the document *is* the
  appealed decision. Relevance now follows the holding; appendix entities are always
  `mentioned`. See the [extract worker](/pipeline/extract.md).

## Deferred: modelling the prior instance

The appealed-from body, its date and its diarienummer are **not** modelled as structured
columns, and no `EntityType` for a deciding body was added. Lower-instance identifiers
(`SS 2025-0135`, `SS § 70`) are not extracted.

Nothing in the [PRD](/prd.md) asks for it, and the anchors have only been verified
against the corpus sample — not all ~1073 documents. Revisit once segmentation has run
over the full corpus and the `Bilaga` layout is known to hold. Until then the appendix
is retrievable prose, correctly attributed, which is enough to answer questions about
the instance below.
