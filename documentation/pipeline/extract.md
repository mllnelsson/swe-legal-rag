---
type: Service
title: Extract Worker
description: Subscriber worker that extracts entities, declared keywords, and cross-references from document text into the graph-in-Postgres tables, then enqueues chunk tasks.
resource: packages/worker-extract
tags: [pipeline, worker, extract, entities, keywords, references, graph]
timestamp: 2026-08-16T00:00:00Z
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
[retrieval agent](/retrieval/chat-agent.md).

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

The length threshold (`factory._is_result_complete`) sizes `min_expected` off
`len(segments.body)` alone, but counts entities found across **body and appendices
together**. Before the appendix-label fix in [document
structure](/reference/document-structure.md), `segments.appendices` came back empty for
22 of 25 documents on the 25-document sample the corpus stood at on 2026-08-04 — not
because their appendix text was gone, but because it had
been swallowed into `trailer`, which this strategy never scans. Entity count dropped
(appendix-sourced entities were simply never found) while the threshold, sized off `body`
alone, did not — so the check judged those results incomplete more often than the body-only
extraction actually warranted, and paid for an LLM call on the strength of a wrong count.
Post-fix, appendix entities count toward the total again, so the same threshold is met more
often on its own. See [structural fields are parsed, not
inferred](/decisions/structural-fields-are-parsed.md) for why structural fields stay
rule-only regardless, and where LLM fallback is the right call instead.

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
- **Regulations:** kyrkoordningen citations, matched over whitespace-collapsed text so a
  line-wrapped citation still resolves — `X kap. Y §` (before or after the statute's
  name, both spelled `kyrkoordningen` and abbreviated `KO`), `KO X:Y`, the spelled-out
  `kyrkoordningen kapitel X § Y`, and a chapter-only citation (`X kap. kyrkoordningen`).
  Ranges are recognised both ways the corpus writes them (`57 kap. 8-19 §§`, `57 kap. 8
  och 19 §§`), and an optional sub-clause (`tredje stycket`, `p. 4`) is matched so the
  citation is not cut short, then dropped from the stored form. `KO` is matched
  case-sensitively and word-anchored: lower-cased it is an ordinary Swedish noun, and
  requiring the statute's name at all is what keeps tryckfrihetsförordningen, OSL,
  rättegångsbalken and kyrkolagen — all cited in the identical `N kap. M §` shape — out of
  the regulation vocabulary. `_canonical_regulations` normalises every match to one
  spelling, **`N kap. M § kyrkoordningen`** (`N kap. kyrkoordningen` with no section).
  The sub-clause is dropped, since `58 kap. 18 §` and `58 kap. 18 § tredje stycket` cite
  the same provision and keeping them apart would fragment the vocabulary the entity graph
  exists to join on. Measured on the 25-document sample the corpus stood at on
  2026-08-04 — the evidence behind this fix, not a claim about the corpus's current
  size: 213 of 215 citations put the lagrum first (`58 kap. 1 § kyrkoordningen`), which
  the patterns previously did not match at all — `EntityType.REGULATION` went from an
  empty vocabulary (0 rows, 0 documents) to 104 rows across 59 distinct names in 24 of
  25 documents; the 25th genuinely cites no lagrum.

  A range is normalised, then **expanded when short**: a numeric range of at most 6
  provisions becomes one entity per section, so `47 kap. 1-3 §§` and `47 kap. 1 §` collapse
  to the same vocabulary rather than sitting beside it as two overlapping ones. A longer
  range stays whole — `57 kap. 8-19 §§` is the header lagrum line of 54 decisions, the
  statutory basis of the appeal rather than a targeted citation, and splitting it into
  twelve entities would bury the provisions a decision actually turns on.

  Once every citation on a document has been canonicalised, `_drop_subsumed_regulations`
  removes what another citation on the same document already covers: a range strictly
  contained in another range of the same chapter (`57 kap. 8-18 §§` given `57 kap. 8-19
  §§`), and a bare `N kap. kyrkoordningen` when the document also cites any section of that
  chapter. Only ranges are ever dropped into a range — a single section is never subsumed,
  since the long ranges left unexpanded are broad statutory bases and `8 kap. 12 §` has to
  survive next to `8 kap. 7-39 §§`. Subsumption runs over the whole merged entity list
  (holding, body and appendices together), since whether a chapter is also cited at section
  level is a fact about the decision, not about the segment a citation happened to sit in.
  Measured against the corpus as it stood when subsumption was added (185 documents,
  before the later duplicate-decision cleanup — see [deployment
  state](/reference/deployment-state.md) for today's count): regulation links went from
  673 to 626, and decision 5/2021's Lagrum list from 10 entries to 6.
- **Parishes:** a bounded run of up to three **capitalised** words immediately before
  `församling`, `stift`, or `pastorat` — a lower-case word cannot join the run, which is
  what stops `Kyrkofullmäktige i Y församling` from matching past `Y`. Leading
  sentence-openers, prepositions and role nouns (words already extracted as their own
  `ROLE` entity, like `kyrkofullmäktige`) are stripped from the front of the match before
  the name is built, so one mention no longer produces three overlapping entities
  (`kyrkofullmäktige i y församling`, `beslut kyrkofullmäktige i y församling`, `motpart
  kyrkofullmäktige i y församling`) for what is one parish. The name is built from its
  remaining words rather than echoed from the source, so the head noun is always spelled
  the same way regardless of source casing. `pastorat` is a recognised head noun — the
  corpus names one 224 times. Measured against that same 185-document snapshot: distinct
  parish entities went from 122 to 43. 134 of those 185 decisions were anonymised, so
  most of this vocabulary is the placeholders `x stift` and `y församling`/`y pastorat`
  — that is the corpus describing itself, not the extractor failing.
- **Roles:** exact-word lookup from a known set (`kyrkoherde`, `kyrkoråd`,
  `kyrkofullmäktige`, `biskop`, `domkapitel`, `kontraktsprost`, `domprost`,
  `stiftsstyrelse`) with Swedish definite/genitive suffix handling
- **Legal concepts:** exact-word lookup from a known set (`överklagande`, `behörighet`,
  `jäv`, `verkställighet`, `tjänstetillsättning`, `överklaganderätt`,
  `tjänsteförseelse`, `disciplinärende`) with the same inflection handling
- **Cross-references:** two identifier spaces, both scanned in **`segments.body`
  only**. A citation is an **anchor word followed by a list**, not a single number: the
  corpus writes "nämndens beslut 13/2011, 31/2011 och 16/2015", and a pattern requiring
  the anchor before every item found only the first. `_cited_identifiers()` matches the
  anchor once, then walks the identifiers after it while a separator
  (`,`/`och`/`samt`/`respektive`, `_REF_LIST_SEPARATOR_RE`) keeps introducing another —
  every item shares the anchor's own sentence as `reference_context`, since the second
  item of a list has no context of its own worth keeping. One line break is tolerated
  wherever a space is, because the PDF wraps mid-list.
  - `_CASE_ANCHOR_RE`/`_CASE_IDENT_RE` — `ÖN`, optionally preceded by `ärende(t/n)` and
    followed by `dnr`, then `YYYY-NNNN` → canonicalised by `normalize_case_number`.
  - `_DECISION_ANCHOR_RE`/`_DECISION_IDENT_RE` — `beslut(et/en)`, then a beslutsnummer in
    either order the corpus writes it: number-first (`13/2025`, and the hyphen spelling
    `13-2025`) or **year-first** (`2022/15`) — the order the registry's own listing
    headlines use (see [corroborating source: the crawler
    headline](/reference/document-structure.md#corroborating-source-the-crawler-headline)).
    Canonicalised by `shared.segmentation.normalize_cited_decision_number`, which is why
    the anchor is not optional: year-first has the same shape as an ärendenummer
    citation, and only the anchor word says which space it is in. See [identifier
    spaces](/reference/document-structure.md#identifier-spaces) for the corpus evidence
    that this reads as beslutsnummer, not ärendenummer.

  Both identifier patterns keep the guard `shared.segmentation` already applies — a
  following date component disqualifies the match (`beslutet 2024-10-\n14` is a date,
  not decision 10/2024) — using `\s*` rather than `[ \t]*` because the corpus wraps a
  citation across that exact boundary.

  Measured over the same 185-document snapshot as the subsumption and parish figures
  above (before the later duplicate-decision cleanup): identifiers extracted rose from
  54 to 116, with zero previously-found citations lost.

  Excluding the trailer is what stops a decision citing itself: it holds the document's
  own `Ärendenummer:` and `Beslut:` lines. Excluding appendices matters because a
  citation there is the *lower instance* citing something, not Överklagandenämnden.
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
`document_entities` row (upgrading `mentioned` → `primary` if re-seen as primary). It then
calls `document_entity.delete_missing_for_document(session, document_id, written_ids)`
with the entity ids it just wrote, deleting any of this document's `document_entities`
rows pointing elsewhere — so re-extracting a document **replaces** its entity set rather
than adding to it. Without this, re-running extraction after a rule change (like the
regulation or parish rules above) would add the corrected entities and leave the
superseded ones sitting beside them, indistinguishable from the fix not having worked.
Rows in [`entities`](/data-model/entities.md) itself are left alone: an entity no document
links to is unreachable, not wrong, and stays available if a later document cites it
again.

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
