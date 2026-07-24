---
type: Service
title: Extract Worker
description: Subscriber worker that extracts entities and cross-references from document text into the graph-in-Postgres tables, then enqueues chunk tasks.
resource: packages/worker-extract
tags: [pipeline, worker, extract, entities, references, graph]
timestamp: 2026-07-24T00:00:00Z
---

# Extract Worker (`packages/worker-extract/`)

Long-running subscriber. Consumes extract tasks, extracts entities and cross-references
from [`documents.raw_text`](/data-model/documents.md), stores them in
[entities](/data-model/entities.md),
[document_entities](/data-model/document-entities.md),
[document_references](/data-model/document-references.md), and
[unresolved_references](/data-model/unresolved-references.md), and enqueues chunk tasks.
This populates the graph-in-Postgres layer used by the
[retrieval agent](/retrieval/agent.md).

## Module layout

| Module | Role |
|---|---|
| `models.py` | `ExtractedEntity`, `ExtractedReference`, `ExtractionResult` DTOs. Re-exports `EntityType`/`EntityRelevance` from `shared.enums` (single source of truth). |
| `entities.py` | `normalize_entity_name()` and `deduplicate_entities()` — one shared helper used across the package (previously three copies). |
| `parsing.py` | `parse_llm_response(raw_json) -> ExtractionResult` — validates types/relevance, normalizes names, deduplicates keeping highest relevance. |
| `extractors/base.py` | `ExtractionStrategy` Protocol: `async extract(document_text, case_number=None) -> ExtractionResult`. |
| `extractors/rule_based.py` | Pure functions + `RuleBasedStrategy` — regex extraction, handles Swedish inflections. |
| `extractors/llm.py` | `LLMStrategy` — constructor-injected `LLMProvider`, delegates to `ai.extract_entities()`. |
| `extractors/factory.py` | `ExtractStrategyMode` StrEnum; `get_extraction_strategy()` factory; `_FallbackStrategy` merge logic. |
| `services/entity_service.py` | `persist_entities()` — deduplicates and upserts to `entities` + `document_entities`. |
| `services/reference_service.py` | `process_references()`, `reconcile_references()` — routes references and reconciles lazy-unresolved refs. |
| `services/extraction_service.py` | `process_extraction()` — validates + runs strategy + persists inside a `body()` wrapped by the shared task envelope. |
| `config.py` | `ExtractSettings(BaseSettings)` — `EXTRACT_TOPIC`, `EXTRACT_NEXT_TOPIC`. |
| `__main__.py` | Entry point — wires repos, registers handler, calls `subscriber.start()`. |

## Extraction strategies

Selected by `EXTRACT_STRATEGY` (default `rule_based_with_llm_fallback`):

| Value | Behaviour |
|---|---|
| `rule_based` | Only regex-based extraction — fast, no LLM cost |
| `llm` | Only LLM extraction via `ai.extract_entities()` |
| `rule_based_with_llm_fallback` | Rule-based first; LLM runs only when the result is incomplete (zero entities or count below a length threshold); merged with rule-based winning deduplication |

### Rule-based extraction

Pure functions, no I/O:
- **Regulations:** `kyrkoordningen X kap. Y §`, `kyrkoordningen kapitel X`, `KO X:Y`
- **Parishes:** `X församling`, `X stift`, `församlingen i X`
- **Roles:** exact-word lookup from a known set (`kyrkoherde`, `kyrkoråd`,
  `kyrkofullmäktige`, `biskop`, `domkapitel`, `kontraktsprost`, `domprost`,
  `stiftsstyrelse`) with Swedish definite/genitive suffix handling
- **Legal concepts:** exact-word lookup from a known set (`överklagande`, `behörighet`,
  `jäv`, `verkställighet`, `tjänstetillsättning`, `överklaganderätt`,
  `tjänsteförseelse`, `disciplinärende`) with the same inflection handling
- **Cross-references:** `_CASE_REF_RE` matches `ÖN YYYY-NNNN` with optional `dnr` prefix;
  extracts the surrounding sentence as `reference_context`
- **Relevance heuristic:** entities in the latter 60% of the document are `primary`;
  earlier occurrences are `mentioned`

## Persistence and reference reconciliation

`persist_entities()` deduplicates within the batch (primary beats mentioned), upserts
each entity (`entity.upsert`, unique on `name, type`), then upserts the
`document_entities` row (upgrading `mentioned` → `primary` if re-seen as primary).

`process_references()` skips self-references, then for each reference looks up its
`case_number` in `documents.case_number`: found → `document_references` (idempotent);
not found → `unresolved_references` (idempotent on
`(source_document_id, target_case_number)`). `reconcile_references()` runs after
extraction for the current document's own `case_number`, promoting matching
`unresolved_references` rows to `document_references` and deleting the unresolved rows.
This is how [unresolved references](/data-model/unresolved-references.md) are lazily
resolved.

`process_extraction()` defines a `body()` handed to the shared task envelope (see
[worker patterns](/pipeline/worker-patterns.md)); it does not re-raise on failure
(`reraise` at its default `False`).
