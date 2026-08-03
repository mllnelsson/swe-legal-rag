---
type: Service
title: Extract Worker
description: Subscriber worker that extracts entities, declared keywords, and cross-references from document text into the graph-in-Postgres tables, then enqueues chunk tasks.
resource: packages/worker-extract
tags: [pipeline, worker, extract, entities, keywords, references, graph]
timestamp: 2026-08-03T00:00:00Z
---

# Extract Worker (`packages/worker-extract/`)

Long-running subscriber. Consumes extract tasks, segments
[`documents.raw_text`](/data-model/documents.md) via
[`shared.segmentation`](/reference/document-structure.md), extracts entities, declared
keywords and cross-references, stores them in
[entities](/data-model/entities.md),
[document_entities](/data-model/document-entities.md),
[document_references](/data-model/document-references.md), and
[unresolved_references](/data-model/unresolved-references.md), and enqueues chunk tasks.
This populates the graph-in-Postgres layer used by the
[retrieval agent](/retrieval/agent.md).

## Module layout

| Module | Role |
|---|---|
| `entities.py` | `normalize_entity_name()` and `deduplicate_entities()` — one shared helper used across the package (previously three copies). |
| `parsing.py` | `parse_llm_response(raw_json) -> ai.dtos.EntityResult` — validates types/relevance, normalizes names, deduplicates keeping highest relevance. |
| `extractors/base.py` | `ExtractionStrategy` — a type alias, `Callable[[DocumentSegments, str \| None], Awaitable[EntityResult]]`, not a Protocol: the interface is one call, so a class would add a name and an instantiation and nothing else. Strategies take `DocumentSegments` so each decides what appendices mean to it. |
| `extractors/rule_based.py` | Pure functions + `extract_rule_based_strategy` — regex extraction, handles Swedish inflections. |
| `extractors/llm.py` | `extract_with_llm(segments, case_number=None, *, provider)` — delegates to `ai.extract_entities()` with **`segments.body`** only. |
| `extractors/factory.py` | `create_extraction_strategy()` — builds the `ExtractStrategyMode`-selected strategy, composing `functools.partial`s for the two LLM-backed modes. |
| `services/entity_service.py` | `persist_entities()` — deduplicates and upserts to `entities` + `document_entities`. |
| `services/reference_service.py` | `process_references()`, `reconcile_references()` — routes references and reconciles lazy-unresolved refs. |
| `services/extraction_service.py` | `process_extraction()` — validates + runs the injected `strategy` + persists inside a `body()` wrapped by the shared task envelope. |
| `config.py` | `ExtractSettings(BaseSettings)` — `EXTRACT_TOPIC`, `EXTRACT_NEXT_TOPIC`, `EXTRACT_STRATEGY` (`ExtractStrategyMode`). |
| `__main__.py` | Entry point — `subscribe()` wires repos, builds the strategy once via `create_extraction_strategy()`, and registers the handler; `main()` calls `shared.worker.serve()`. |

Entity and reference DTOs (`ExtractedEntity`, `ExtractedReference`, `EntityResult`) live
in [`ai.dtos`](/packages/ai.md) — this package has no DTOs of its own, since they were an
identity copy of the `ai` ones under different names.

## Extraction strategies

Selected by `EXTRACT_STRATEGY` (default `rule_based_with_llm_fallback`, typed as
`ExtractStrategyMode`). An unrecognised value is **fatal at startup**, naming the bad
value, rather than silently falling back to the default:

| Value | Behaviour |
|---|---|
| `rule_based` | Only regex-based extraction — fast, no LLM cost |
| `llm` | Only LLM extraction via `ai.extract_entities()` |
| `rule_based_with_llm_fallback` | Rule-based first; LLM runs only when the result is incomplete (zero entities or count below a length threshold); merged with rule-based winning deduplication |

`create_extraction_strategy()` is called **once per process**, at `subscribe()` time —
not once per document. The two LLM-backed modes build their `LLMProvider` there and
close over it with `functools.partial`; `process_extraction()` takes the resulting
`strategy` as a required parameter rather than looking one up inside the step body, the
same "build once, inject" pattern every other worker uses for its provider — see
[worker patterns](/pipeline/worker-patterns.md).

### When the `structured` role has no model

If [`llm_config.yaml`](/reference/llm-config.md) resolves `structured` to `kind: none`,
`create_extraction_strategy()` decides what that means at startup — the same moment it
picks a provider — rather than letting each document reach one that refuses:

| Value | Behaviour with no model |
|---|---|
| `rule_based` | Unchanged; it never built a provider |
| `rule_based_with_llm_fallback` | Degrades to its regex half, with a warning. The mode already treats the model as optional, and an off switch you have to remember to set twice is not an off switch |
| `llm` | **Refuses to start** (`LLMDisabledError`). It was asked for explicitly, and quietly running the regex pass instead would run something the operator did not ask for, on a step whose output nothing downstream re-checks |

This is what lets the pipeline run crawl through extract with no API key configured.

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
- **Cross-references:** two identifier spaces, both canonicalised by
  `shared.segmentation`, both scanned in **`segments.body` only**:
  - `_CASE_REF_RE` matches `ÖN YYYY-NNNN` with optional `dnr` prefix → `YYYY-NNNN`
  - `_DECISION_REF_RE` matches `beslut N/YYYY` → `N/YYYY`

  The surrounding sentence is kept as `reference_context`. Excluding the trailer is what
  stops a decision citing itself: it holds the document's own `Ärendenummer:` and
  `Beslut:` lines. Excluding appendices matters because a citation there is the *lower
  instance* citing something, not Överklagandenämnden.
- **Relevance:** entities found in `segments.holding` are `primary`; everything else in
  the body is `mentioned`. Entities are also extracted from **appendices**, always as
  `mentioned` — the appealed decision's entities stay findable via the pre-filter but can
  never outrank the nämnd's own.

  The former heuristic promoted anything past 60% of the document. An appendix inverts
  it: the tail of the document *is* the appealed decision. See
  [appendices are labelled, not dropped](/decisions/appendix-segmentation.md).

## Declared keywords (outside the strategy switch)

The trailer's `Sökord:` line is the nämnd's own subject classification, not something
extraction infers — so it is read deterministically by
[`shared.segmentation.parse_keywords(segments.trailer)`](/reference/document-structure.md)
in every `EXTRACT_STRATEGY` mode alike, rather than through `ExtractionStrategy`. Each
value becomes an `ExtractedEntity(type=EntityType.KEYWORD, relevance=PRIMARY)` — always
`PRIMARY`, since a declared keyword is never merely mentioned — and is persisted through
the same `persist_entities()` call as the strategy's own entities.

Any `keyword`-typed entity a strategy itself emits is dropped before persistence. The
trailer is the only source of truth for a keyword, so a strategy producing one — most
plausibly the `llm` mode, since `parsing.py` validates against every member of
`EntityType` and would otherwise let it through — has invented a declared field rather
than inferred one, and would silently create a second path to the same data if kept.

## Persistence and reference reconciliation

`persist_entities()` deduplicates within the batch (primary beats mentioned), upserts
each entity (`entity.upsert`, unique on `name, type`), then upserts the
`document_entities` row (upgrading `mentioned` → `primary` if re-seen as primary).

`process_references()` skips any reference matching one of the document's **own**
identifiers (`case_number` or `decision_number`), then resolves the rest. Because the
two canonical formats are disjoint — a beslutsnummer always contains `/` — the reference
string alone says which column to try: `documents.decision_number` if it has a slash,
`documents.case_number` otherwise. Found → `document_references` (idempotent); not found
→ `unresolved_references` (idempotent on `(source_document_id, target_case_number)`).

`reconcile_references()` runs after extraction for **both** of the current document's
identifiers, promoting matching `unresolved_references` rows to `document_references`
and deleting the unresolved rows. A parked row whose source is this same document is
discarded rather than promoted — `document_references` has a composite primary key over
`(source, target)`, so it would become a self-edge. This is how
[unresolved references](/data-model/unresolved-references.md) are lazily resolved.

`process_extraction()` defines a `body()` handed to the shared task envelope (see
[worker patterns](/pipeline/worker-patterns.md)); it does not re-raise on failure
(`reraise` at its default `False`).
