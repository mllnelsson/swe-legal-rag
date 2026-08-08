---
type: Reference
title: Decision Document Structure
description: The anatomy of an Överklagandenämnden decision PDF — header, holding, trailer and appendices — and the anchors the pipeline segments it with.
resource: packages/shared/src/shared/segmentation.py
tags: [segmentation, parsing, appendix, bilaga, corpus]
timestamp: 2026-08-07T00:00:00Z
---

# Decision Document Structure

Överklagandenämnden publishes **one PDF per ärende**, and that PDF physically contains
the decision that was appealed. The [crawl source](/reference/crawl-source.md) offers no
separate appendix files: decision and appendix arrive as one document, flattened by the
[parse worker](/pipeline/parse.md) into a single `documents.raw_text`.

Read this before touching `shared/segmentation.py`, the
[metadata](/pipeline/metadata.md), [extract](/pipeline/extract.md) or
[chunk](/pipeline/chunk.md) workers. The anchors below are deliberately regexes rather
than model calls — see [structural fields are parsed, not
inferred](/decisions/structural-fields-are-parsed.md) for why, and what that decision
assumes about the corpus staying this regular.

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
…………………………………………………………              <- trailer rule (ellipsis, dots or dashes)
BILAGA A                            <- label; 22/25 corpus decisions write it upper case
<the prior instance's own document, verbatim>
```

The trailer's field order is not fixed either — most decisions write
`Sökord > Ärendenummer > Beslut`, but at least one writes `Ärendenummer > Beslut > Sökord`.
See Anchors below for how the parser copes with either ordering.

## Segments

`shared.segmentation.split_document(raw_text) -> DocumentSegments` cuts this into four
parts. It is pure — no I/O, no config — and never raises: a document matching none of
the anchors comes back as a single `body`.

| Segment | Contents | Who wrote it |
|---|---|---|
| `body` | Header through the holding, trailer excluded | Överklagandenämnden |
| `holding` | The slice of `body` after `Överklagandenämndens beslut:` | Överklagandenämnden |
| `trailer` | `Sökord` / `Ärendenummer` / `Beslut` | Överklagandenämnden (metadata + keywords) |
| `appendices` | One `Appendix(label, text)` per `BILAGA X` / `Bilaga X` | **The appealed instance** |

## Anchors

Resolved most-reliable-first:

1. **Trailer** — a line-initial `Sökord:` or `Ärendenummer:`, whichever comes **first in
   the document**: the *earliest* match wins, not the first pattern tried. The corpus does
   not fix the trailer's field order (see Anatomy above), and anchoring on whichever
   pattern happens to be checked first cut the trailer short in a decision that orders it
   `Ärendenummer > Beslut > Sökord` — the anchor landed on `Sökord:`, which was the
   trailer's *last* line there, leaving the document's own identifiers in `body` where
   they defeat the self-citation guard the trailer split exists to provide. `Beslut:` is
   deliberately not an anchor: it is never the first trailer line in the corpus, and an
   appended lower-instance protocol uses `Beslut:` as a heading of its own. Once found,
   this definitively ends the nämnd's own document, so `body` ends where it begins. A
   match inside an appendix is ignored: an appended lower-instance decision can carry a
   trailer of its own.
2. **Appendices** — a line that is *only* a label:
   `^[ \t]*(?i:bilaga)[ \t]+(\d{1,2}|[A-ZÅÄÖ])[ \t]*$`. Case-insensitive on the word
   alone — the identifier itself stays upper case, so a stray `bilaga a` in prose still
   cannot masquerade as a label. The corpus writes the word both ways: `BILAGA A` in
   22 of 25 decisions, `Bilaga A` in the rest. `Appendix.label` is **built** from a
   canonical `Bilaga <id>` prefix rather than echoed from the source, so it is always one
   spelling regardless of which the source used — this is what keeps
   `chunks.appendix_label` a stable join key. The end anchor is essential. Decision prose
   references appendices constantly ("markerade med rött i bilagan", "enligt bilaga 1"),
   and an unanchored match would split the document mid-sentence.
3. **Fallbacks** — no trailer: cut at the first appendix label instead. Neither: the
   whole text is `body`.

Line endings are normalised to LF first. Parsed PDFs mix CRLF and LF, and a stray CR
before the newline defeats every end-of-line assertion above.

The trailer rule — a run of ellipsis characters, plain dots, or dashes, drawn all three
ways in the corpus — is stripped from the trailer as a whole line, so a `Sökord:` value
ending in a full stop survives.

## Holding anchor

`_HOLDING_RE` matches either `Överklagandenämndens beslut:` followed by the ruling text,
or the same three words alone on their own line with no colon — two decisions in the
corpus write it that way and would otherwise lose `holding` (and with it
`decision_outcome` and every PRIMARY entity) entirely. Requiring the colon *or* end of
line is what keeps this from matching the in-prose citation "Överklagandenämndens beslut
8/01", which names a different decision: that phrase is never alone on its line and never
ends in a colon.

## Trailer fields

`shared.segmentation.parse_trailer_fields(trailer) -> dict[TrailerField, str]` reads the
trailer's labelled lines into a dict, keyed by the `TrailerField` StrEnum (`Sökord`,
`Ärendenummer`, `Beslut`). It is line-oriented rather than one regex per field: because the
corpus does not fix the trailer's field order (see Anchors above), a pattern that ends a
value by naming the labels that may follow it is wrong for whatever ordering it did not
anticipate, and getting it wrong runs the value to the end of the document, swallowing the
appendix — the same failure mode the trailer-start anchor above had to be fixed for. A
value the PDF wraps onto a following line is folded back onto its field; a blank line or
the trailer rule ends it. Never raises: a missing trailer, or one with no labelled line,
comes back `{}`.

`shared.segmentation.parse_keywords(trailer) -> list[str]` reads the `Sökord` field through
`parse_trailer_fields` and turns it into the case's declared subject keywords — the
[extract worker](/pipeline/extract.md) persists them as [entities](/data-model/entities.md)
of type `keyword`. Every `Sökord:` line in the corpus separates its values with a **full
stop**, not `,`/`;` — the old comma/semicolon-only separator had never actually split
anything, and 12 of 25 corpus decisions stored a merged value like `"Kyrkobyggnad.
Kyrkorum"` as a single keyword. A stop separates only before whitespace followed by a
capital letter, or at the end of the value; `,` and `;` still work as the conventional
spelling; **whitespace alone never separates**, so a multi-word keyword like `Utlämnande av
handling` stays one entry; and a lookbehind keeps an abbreviation like `Avskrivning m.m.`
from being split apart or truncated to `Avskrivning m.m`. Values are whitespace-collapsed,
de-duplicated case-insensitively, and returned in document order. Like the rest of this
module it never raises — a missing trailer, one with no `Sökord` field, or an empty value
all come back as `[]`.

## Identifier spaces

A decision carries **two** identifiers, and citations in the corpus use either:

| | Example | Column | Canonicaliser |
|---|---|---|---|
| Ärendenummer | `ÖN 2025-0017`, `ÖN 2026-04`, `ÖN 2021/2` | `documents.case_number` | `normalize_case_number` → `2025-0017`, `2026-0004`, `2021-0002` (sequence zero-padded to 4 digits) |
| Beslutsnummer | `1/2026`, `23-2026` | `documents.decision_number` | `normalize_decision_number` → `1/2026`, `23/2026` |

The canonical **stored** forms are **disjoint** — a beslutsnummer always contains `/`, an
ärendenummer never does — so a reference string says for itself which column can resolve
it. That is why `ExtractedReference` carries no separate "kind" field. See
[document references](/data-model/document-references.md) and the
[extract worker](/pipeline/extract.md).

This holds even though a *raw* ärendenummer can be written with a slash: the registry
wrote `ÖN 2021/2` throughout 2020–2021 and sporadically after, and slash and hyphen are
two spellings of one identifier space, not two registries — decisions 29/2020 and
30/2020 carry `ÖN 2020-37` and `ÖN 2020-36`, and 1/2021, the final decision in the same
matter, lists `ÖN 2020/36, ÖN 2020/37, ÖN 2020/39`. `normalize_case_number` canonicalises
either separator to the same hyphenated `YYYY-NNNN`, so the stored column never carries a
slash regardless of which spelling the trailer used.

Canonicalising both spellings is what makes self-reference detection work at all:
before it, `worker-metadata` stored `2025-0017` while the extractor yielded
`ÖN 2025-0017`, so the equality guard never fired and no cross-reference ever resolved.

`_DECISION_NUMBER_RE` accepts both the `N/YYYY` spelling and the hyphen spelling `N-YYYY`
one corpus decision uses (`Beslut: 23-2026`); both halves are length-bounded and
word-anchored so the hyphen form cannot swallow an ärendenummer, a date, or a mandate
period.

`normalize_case_number` zero-pads the sequence to four digits, so `ÖN 2026-04` stores as
`2026-0004`. Unpadded, a citation written the long way could never resolve to a document
stored the short way, or vice versa; there is no collision across the corpus, but the
assumption behind padding is that the registrar never issues `2026-04` and `2026-0004` as
*distinct* ärenden in the same year. This fix had to land after the date guard below —
padding first would have turned a swallowed date into a plausible-looking `2026-0004`
rather than an obviously wrong one.

`_CASE_NUMBER_RE` accepts a hyphen, en dash, or slash as the year/sequence separator, and
also guards against reading a date or a mandate period as an ärendenummer, which matters
because the body fallback runs this over free prose, not just the labelled trailer line. A
sequence that is itself a year of this era is rejected — the mandate period
`mandatperioden 2026-2029` no longer parses as case `2029` of `2026` — and a
following date component disqualifies the match — `Meddelat 2026-04-08` no longer parses as
case `4` of `2026`. Case `1234` of `2020-1234` still parses.

## Corroborating source: the crawler headline

The OData listing gives each decision a headline of the form `Beslut 2026-23  Avskrivning`
(year-first — the reverse of the trailer's `Beslut: 23/2026` — and occasionally
double-spaced): the beslutsnummer and the decision's title concatenated.
`shared.source_headline.parse_source_headline(headline) -> SourceHeadline | None` splits it
into `decision_number` (canonicalised into the same `N/YYYY` space as
`normalize_decision_number`, so the two are directly comparable) and `title`;
`headline_title(headline)` returns the title alone, falling back to the headline unchanged
if it is not in that shape.

**Precedence: the document's own trailer wins; the headline is a fallback.** The PDF is the
authoritative artefact — `source_headline` is a listing field the crawler copied, not a
second measurement of the decision. `worker-metadata`'s `extract_decision_number` only
falls through to the headline when neither the trailer nor the body has one; `extract_category`
prefers the PDF header the same way, and prefers its content even when both exist — the
PDF's `Avskrivning m.m.` against the listing's bare `Avskrivning`. See [metadata
worker](/pipeline/metadata.md). The two sources agree across the whole corpus (25/25), so
this ordering has never actually been tested by a real disagreement; `worker-metadata` logs
a WARNING if the two ever diverge, and another if neither source has a decision number at
all.

No new column and no new DTO field came from this: `documents.source_headline` stays
verbatim, because that column's contract is "what the listing said." Splitting only happens
where a headline is projected to a client — see [documents](/data-model/documents.md).

## Drift reporting

`shared.segmentation.find_segmentation_gaps(segments) -> list[SegmentationGap]` names which
of a document's structural anchors did not fire, against an already-built
`DocumentSegments` — `NO_TRAILER`, `NO_HOLDING`, `NO_APPENDIX`, `NO_KEYWORDS`. A gap is not
an error: `split_document` never raises, and a document genuinely laid out differently is a
thing that happens. It is a signal for whoever reads the worker logs that an anchor stopped
matching — the class of defect every fix on this page used to produce with no signal at
all, either `None` or a plausible wrong value. `worker-metadata` is the only caller,
logging it once at the metadata step since [extract](/pipeline/extract.md) and
[chunk](/pipeline/chunk.md) segment the same text again (see [metadata
worker](/pipeline/metadata.md)). Verified steady state across the corpus: zero warnings on
all 25 documents.

## Why the split matters

Everything downstream reads a different slice, and each has a reason:

* **[metadata](/pipeline/metadata.md)** — trailer then body, never appendices. An
  appended decision has its own date, outcome and diarienummer.
* **[extract](/pipeline/extract.md)** — references from `body` only; entities from
  `body` *and* appendices, but appendix entities are always `mentioned`; keyword entities
  from `trailer` alone, via `parse_keywords`.
* **[chunk](/pipeline/chunk.md)** — body and each appendix chunked separately and
  labelled; the trailer is not chunked at all.
* **[retrieval](/retrieval/agent.md)** — searches `body` chunks by default, per the
  [body-first retrieval decision](/decisions/body-first-retrieval.md).

The failure this prevents is concrete. In the corpus sample
`d5448279-…/original.pdf`, 4 534 of 19 649 characters are the stift's own decision
arguing **for** secrecy — an argument Överklagandenämnden went on to overturn.
Unsegmented, that text was chunked, embedded, retrieved and cited under the nämnd's
case number with nothing marking whose words it was.
