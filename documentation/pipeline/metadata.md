---
type: Service
title: Metadata Worker
description: Subscriber worker that extracts structured metadata (case number, decision number, date, outcome, category) rule-based first with an LLM fallback for missing fields.
resource: packages/worker-metadata
tags: [pipeline, worker, metadata, extraction, llm]
timestamp: 2026-08-04T00:00:00Z
---

# Metadata Worker (`packages/worker-metadata/`)

Long-running subscriber. Consumes metadata tasks, extracts structured metadata from
[`documents.raw_text`](/data-model/documents.md) using rule-based patterns first and an
LLM fallback for missing fields only, updates the document record, and enqueues extract
tasks.

## Module layout

| Module | Role |
|---|---|
| `config.py` | `MetadataSettings(BaseSettings)` — `METADATA_TOPIC` (`metadata`), `METADATA_NEXT_TOPIC` (`extract`). `get_metadata_settings()` is `@lru_cache`. |
| `patterns.py` | `MetadataResult` dataclass + per-field pure extraction functions + `extract_metadata_rule_based()` + `is_complete()`. Field extractors take `DocumentSegments`, not raw text. |
| `service.py` | `process_metadata()` async function — orchestration via functional DI. |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, defines the `_llm_extractor` closure, registers the handler, calls `subscriber.start()`. |

## Extraction strategy

Two-stage extraction, rule-based first, LLM fallback only for fields left `None`.

Everything runs on segments from
[`shared.segmentation`](/reference/document-structure.md), so an appended lower-instance
decision can never contribute its own date, outcome or diarienummer.

1. **Rule-based (`patterns.py`)** — per-field pure functions using `re` patterns for
   Swedish legal document formats:
   - `extract_case_number`: reads the trailer's `Ärendenummer` field through
     [`parse_trailer_fields`](/reference/document-structure.md), canonicalised to
     `YYYY-NNNN` (sequence zero-padded to four digits) by `normalize_case_number`.
     Trailer first, body line-regex as fallback, never the appendices.
   - `extract_decision_number(segments, source_headline=None)`: reads the trailer's
     `Beslut` field the same way, canonicalised to `N/YYYY` by `normalize_decision_number`
     (also accepts the hyphen spelling one corpus decision uses, `N-YYYY`). Falls through
     to the [crawler's `source_headline`](/reference/document-structure.md#corroborating-source-the-crawler-headline)
     only when neither the trailer nor the body has one — **the document's own trailer
     always wins**, since the PDF is the authoritative artefact and the headline is a
     listing field the crawler copied.
   - `extract_decision_date`: matches `Meddelat <YYYY-MM-DD>` within the first 2000
     characters **of the body**.
   - `extract_decision_outcome`: returns `segments.holding` — the text after
     `Överklagandenämndens beslut:` — with whitespace collapsed. Falls back to searching
     the body tail for `bifaller/avslår/avvisar överklagandet`.
   - `extract_category(segments, source_headline=None)`: looks for a `Svenska kyrkans
     överklagandenämnd` heading line in the first 10 lines of the body and returns the
     line two positions after it. Falls back to the headline's title (via
     `shared.source_headline.parse_source_headline`) only when the header line is missing
     or empty; the PDF header wins on content even when both exist, since it is the richer
     of the two (`Avskrivning m.m.` against the listing's bare `Avskrivning`).
   - `_from_trailer_or_body` (shared by the two trailer-labelled fields) reads the
     trailer through `parse_trailer_fields`, which is what makes it independent of the
     order a decision lists its trailer fields in — see [document
     structure](/reference/document-structure.md). Line regexes
     (`_CASE_NUMBER_LINE_RE`, `_DECISION_NUMBER_LINE_RE`) are the body fallback only, for
     decisions whose trailer the anchors did not find.
   - `extract_metadata_rule_based(text, source_headline=None)` runs the above over
     `split_document(text)` and assembles the `MetadataResult`; `source_headline` is
     `documents.source_headline`, passed through by `process_metadata`.
   - A broader pattern set (`Dnr`/`Diarienummer` case numbers, Swedish
     textual/abbreviated dates, `Ärende:`/`Ämne:`/`Kategori:` headers) was implemented
     and then narrowed to this verified set; documents that don't match fall through to
     the LLM fallback.
2. **LLM fallback (via the [ai package](/packages/ai.md))** — invoked only when
   rule-based extraction leaves fields `None`, and handed **`segments.body`**, not
   `raw_text`. `_make_llm_extractor(provider)` builds a closure around a
   structured-role provider (`ai.providers.roles.create_structured_llm_provider()`,
   Mistral Small 3.2 via Berget by default); the closure calls
   `ai.services.extract_metadata(...)` and converts `decision_date` from ISO string to
   `datetime.date`.
   `is_complete()` deliberately ignores `decision_number`: it is a nice-to-have for
   reference resolution, never worth paying for an LLM call.
3. **Merge** — rule-based values always win; LLM values only fill remaining `None`
   fields.

All metadata fields are freeform `VARCHAR` — no enum constraints. Missing metadata (all
fields `None`) is a valid outcome; the task still completes.

## Service layer and error handling

`process_metadata(document_id, task_id, document_repo, task_repo, queue_publisher,
rule_extractor, llm_extractor, session, next_topic)` is a module-level async function.
`rule_extractor` is `Callable[[str, str | None], MetadataResult]`, called with
`document.raw_text` and `document.source_headline`; `llm_extractor` is injected the same
way. The service has no knowledge of the concrete LLM provider. LLM failure
is non-fatal (logged as a warning; extraction continues with partial metadata). A missing
document / no `raw_text` raises `StepInputError`. Task lifecycle is owned by the shared
task envelope (see [worker patterns](/pipeline/worker-patterns.md)).

## Drift reporting

`process_metadata` calls `_log_template_drift(document_id, raw_text, source_headline)`
after the rule-based pass, on every document, in every mode — it never changes the
extraction outcome. It re-segments the text and:

1. Logs a WARNING naming any [`SegmentationGap`](/reference/document-structure.md) found
   by `shared.segmentation.find_segmentation_gaps` — the anchors that did not fire on this
   document.
2. Logs a WARNING if no decision number was found anywhere — trailer, body, *and*
   headline.
3. Logs a WARNING if the trailer's decision number and the headline's disagree, naming
   both and stating that the trailer is the one used.

This is logged here and nowhere else, deliberately: metadata is the first pipeline step
that segments the text, and [extract](/pipeline/extract.md) and
[chunk](/pipeline/chunk.md) segment the same text again — three copies of the same warning
would be noise, not signal. Verified steady state across the 25-document corpus: zero
warnings of any of the three kinds.
