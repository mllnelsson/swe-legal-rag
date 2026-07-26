---
type: Reference
title: Decision Document Structure
description: The anatomy of an Överklagandenämnden decision PDF — header, holding, trailer and appendices — and the anchors the pipeline segments it with.
resource: packages/shared/src/shared/segmentation.py
tags: [segmentation, parsing, appendix, bilaga, corpus]
timestamp: 2026-07-26T00:00:00Z
---

# Decision Document Structure

Överklagandenämnden publishes **one PDF per ärende**, and that PDF physically contains
the decision that was appealed. The [crawl source](/reference/crawl-source.md) offers no
separate appendix files: decision and appendix arrive as one document, flattened by the
[parse worker](/pipeline/parse.md) into a single `documents.raw_text`.

Read this before touching `shared/segmentation.py`, the
[metadata](/pipeline/metadata.md), [extract](/pipeline/extract.md) or
[chunk](/pipeline/chunk.md) workers.

## Anatomy

```
Svenska kyrkans överklagandenämnd
Meddelat 2026-01-07
Utlämnande av handlingar            <- category
53 kap. 3-11 §§ kyrkoordningen      <- lagrum (optional)
YRKANDE M.M.
...background, party submissions, the nämnd's reasoning...
Överklagandenämndens beslut:        <- holding anchor
1. Överklagandenämnden avslår överklagandet ...
Sökord: Utlämnande av handlingar.   -.
Ärendenummer: ÖN 2025-0017           |- trailer
Beslut: 1/2026                      -'
…………………………………………………………              <- ellipsis rule
Bilaga A
<the prior instance's own document, verbatim>
```

## Segments

`shared.segmentation.split_document(raw_text) -> DocumentSegments` cuts this into four
parts. It is pure — no I/O, no config — and never raises: a document matching none of
the anchors comes back as a single `body`.

| Segment | Contents | Who wrote it |
|---|---|---|
| `body` | Header through the holding, trailer excluded | Överklagandenämnden |
| `holding` | The slice of `body` after `Överklagandenämndens beslut:` | Överklagandenämnden |
| `trailer` | `Sökord` / `Ärendenummer` / `Beslut` | Överklagandenämnden (metadata) |
| `appendices` | One `Appendix(label, text)` per `Bilaga X` | **The appealed instance** |

## Anchors

Resolved most-reliable-first:

1. **Trailer** — a line-initial `Sökord:`, falling back to `Ärendenummer:`. This
   definitively ends the nämnd's own document, so `body` ends where it begins. A match
   inside an appendix is ignored: an appended lower-instance decision can carry a
   trailer of its own.
2. **Appendices** — a line that is *only* a label: `^[ \t]*Bilaga[ \t]+(\d{1,2}|[A-ZÅÄÖ])[ \t]*$`.
   The end anchor is essential. Decision prose references appendices constantly
   ("markerade med rött i bilagan", "enligt bilaga 1"), and an unanchored match would
   split the document mid-sentence.
3. **Fallbacks** — no trailer: cut at the first appendix label instead. Neither: the
   whole text is `body`.

Line endings are normalised to LF first. Parsed PDFs mix CRLF and LF, and a stray CR
before the newline defeats every end-of-line assertion above.

The ellipsis rule (`…` repeated, occasionally plain dots) is stripped from the trailer
as a whole line, so a `Sökord:` value ending in a full stop survives.

## Identifier spaces

A decision carries **two** identifiers, and citations in the corpus use either:

| | Example | Column | Canonicaliser |
|---|---|---|---|
| Ärendenummer | `ÖN 2025-0017` | `documents.case_number` | `normalize_case_number` → `2025-0017` |
| Beslutsnummer | `1/2026` | `documents.decision_number` | `normalize_decision_number` → `1/2026` |

The canonical forms are **disjoint** — a beslutsnummer always contains `/`, an
ärendenummer never does — so a reference string says for itself which column can resolve
it. That is why `ExtractedReference` carries no separate "kind" field. See
[document references](/data-model/document-references.md) and the
[extract worker](/pipeline/extract.md).

Canonicalising both spellings is what makes self-reference detection work at all:
before it, `worker-metadata` stored `2025-0017` while the extractor yielded
`ÖN 2025-0017`, so the equality guard never fired and no cross-reference ever resolved.

## Why the split matters

Everything downstream reads a different slice, and each has a reason:

* **[metadata](/pipeline/metadata.md)** — trailer then body, never appendices. An
  appended decision has its own date, outcome and diarienummer.
* **[extract](/pipeline/extract.md)** — references from `body` only; entities from
  `body` *and* appendices, but appendix entities are always `mentioned`.
* **[chunk](/pipeline/chunk.md)** — body and each appendix chunked separately and
  labelled; the trailer is not chunked at all.
* **[retrieval](/retrieval/agent.md)** — searches `body` chunks by default, per the
  [body-first retrieval decision](/decisions/body-first-retrieval.md).

The failure this prevents is concrete. In the corpus sample
`d5448279-…/original.pdf`, 4 534 of 19 649 characters are the stift's own decision
arguing **for** secrecy — an argument Överklagandenämnden went on to overturn.
Unsegmented, that text was chunked, embedded, retrieved and cited under the nämnd's
case number with nothing marking whose words it was.
