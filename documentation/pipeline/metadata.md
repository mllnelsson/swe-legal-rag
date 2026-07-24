---
type: Service
title: Metadata Worker
description: Subscriber worker that extracts structured metadata (case number, date, outcome, category) rule-based first with an LLM fallback for missing fields.
resource: packages/worker-metadata
tags: [pipeline, worker, metadata, extraction, llm]
timestamp: 2026-07-24T00:00:00Z
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
| `patterns.py` | `MetadataResult` dataclass + per-field pure extraction functions + `extract_metadata_rule_based()` + `is_complete()`. |
| `service.py` | `process_metadata()` async function — orchestration via functional DI. |
| `__main__.py` | Entry point. Loads `.env`, wires dependencies, defines the `_llm_extractor` closure, registers the handler, calls `subscriber.start()`. |

## Extraction strategy

Two-stage extraction, rule-based first, LLM fallback only for fields left `None`.

1. **Rule-based (`patterns.py`)** — per-field pure functions using `re` patterns for
   Swedish legal document formats:
   - `extract_case_number`: matches `Ärendenummer: ÖN <YYYY-NNN>`.
   - `extract_decision_date`: matches `Meddelat <YYYY-MM-DD>` within the first 2000
     characters.
   - `extract_decision_outcome`: searches near document end for
     `bifaller/avslår/avvisar överklagandet` and returns the surrounding sentence.
   - `extract_category`: looks for a `Svenska kyrkans överklagandenämnd` heading line in
     the first 10 lines and returns the line two positions after it.
   - A broader pattern set (`Dnr`/`Diarienummer` case numbers, Swedish
     textual/abbreviated dates, `Ärende:`/`Ämne:`/`Kategori:` headers) was implemented
     and then narrowed to this verified set; documents that don't match fall through to
     the LLM fallback.
2. **LLM fallback (via the [ai package](/packages/ai.md))** — invoked only when
   rule-based extraction leaves fields `None`. `_make_llm_extractor(provider)` builds a
   closure around a structured-role provider
   (`ai.providers.roles.create_structured_llm_provider()`, Mistral Small 3.2 via Berget
   by default); the closure calls `ai.services.extract_metadata(...)` and converts
   `decision_date` from ISO string to `datetime.date`.
3. **Merge** — rule-based values always win; LLM values only fill remaining `None`
   fields.

All metadata fields are freeform `VARCHAR` — no enum constraints. Missing metadata (all
fields `None`) is a valid outcome; the task still completes.

## Service layer and error handling

`process_metadata(document_id, task_id, document_repo, task_repo, queue_publisher,
rule_extractor, llm_extractor, session, next_topic)` is a module-level async function.
`rule_extractor` and `llm_extractor` are injected callables — the service has no
knowledge of the concrete LLM provider. LLM failure is non-fatal (logged as a warning;
extraction continues with partial metadata). A missing document / no `raw_text` raises
`StepInputError`. Task lifecycle is owned by the shared task envelope (see
[worker patterns](/pipeline/worker-patterns.md)).
