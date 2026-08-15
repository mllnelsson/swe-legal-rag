---
type: Repository
title: Repository Layer
description: The function-based data-access layer bridging SQLAlchemy models and Pydantic DTOs, injected into services as Protocol-typed namespaces.
resource: packages/shared/src/shared/repositories
tags: [data-model, repositories, data-layer, dto, protocol]
timestamp: 2026-08-14T00:00:00Z
---

# Repository Layer

The data-access layer sits between the SQLAlchemy models (DAOs) and the Pydantic
[DTOs](/packages/shared.md): it is the only place ORM objects are touched, and it never
lets them escape upward. It lives in `packages/shared/src/shared/repositories/`.

## Modules of functions, not classes

Repositories are **modules of async functions**, one module per entity (`document`,
`task`, `chunk`, `entity`, `document_entity`, `document_reference`,
`unresolved_reference`, `search`, `session`). Every function takes an `AsyncSession` as
its **first argument** and takes/returns DTOs — never ORM objects. There are no
repository classes.

```python
from shared.repositories import document as document_repo
doc = await document_repo.get_by_id(session, doc_id)
```

**Why functions.** The coding guidelines reserve classes for genuine abstractions
(Protocol/ABC), third-party wrappers, and pydantic/StrEnum/Exception types. The old
repository classes held nothing but injected state — a stateful-class anti-pattern. Free
functions with an explicit `session` parameter are the guideline-compliant form and make
the session/dependency flow explicit.

## Notable functions

- `document.update` — `model_dump(exclude_none=True)`, updating only provided fields
- `document.get_by_source_decision_number` — lookup by the beslutsnummer the *listing
  headline* states, unique unlike the two below. This is the crawl worker's actual dedup
  key: `source_url` and `source_document_id` both identify the listing entry the OData
  API served, and that listing once published decision 21/2021 under two of those.
- `document.get_by_case_number` / `document.get_by_decision_number` — lookup by either
  identifier read from the **PDF itself** (trailer, with a body fallback). Neither is
  declared unique, for two different reasons: an ärendenummer names an *ärende*, and the
  nämnd rules more than once within one (three decisions can share one case number);
  a beslutsnummer really does name one decision, but this column is filled by the
  metadata step from the PDF's own text, which can misread. Both functions order by
  `decision_date` (nulls last, then `id`) and return the earliest match rather than
  raising on a second row — there is no correct row to prefer, but raising failed the
  *citing* document's extract step over an ambiguity in the document it cited.
- `task.update_status` — sets `started_at` on `processing`, `completed_at` on
  `completed`/`failed` (compared against `TaskStatus` members)
- `task.count_by_step_and_status(session)` — `GROUP BY step, status` counts as a
  `dict[(PipelineStep, TaskStatus), int]`, for the end-of-run summary
  `scripts/run_pipeline.py` prints. Counted in the database, not by listing rows: after a
  backfill that is far more tasks than there is reason to load
- `entity.upsert` — check-then-insert on the `(name, type)` unique constraint
- `document_entity.upsert` — check-then-insert; upgrades `mentioned` → `primary`
- `document_entity.delete_missing_for_document(session, document_id, entity_ids)` —
  deletes a document's `document_entities` rows for any entity outside `entity_ids`. Used
  by [`persist_entities()`](/pipeline/extract.md) so re-extracting a document replaces its
  entity set instead of only adding to it; leaves `entities` rows untouched.
- `document_reference.upsert` — idempotent insert on the composite PK
- `unresolved_reference.upsert/get_by_target_case_number/delete` — manages refs pending
  reconciliation
- `chunk.bulk_create` — `session.add_all()` batch insert
- `chunk.update_embeddings(session, updates)` — bulk UPDATE of `embedding`; does not touch
  the GENERATED `tsv` column
- `chunk.vector_search(session, embedding, document_ids, limit)` — pgvector cosine
  distance, filtered to candidates, excludes NULL embeddings
- `chunk.text_search(session, query, document_ids, limit)` —
  `websearch_to_tsquery('swedish', query)` ranked by `ts_rank`
- `search.find_candidate_documents(session, filter, limit=None)` — narrows the corpus via
  metadata WHERE, EXISTS subqueries through `document_entities`→`entities`, and
  `document_references` traversal in both directions; an empty filter returns all
  document IDs with `raw_text`. The optional `limit` bounds how large a candidate set the
  [search API](/api/search.md) will hand its search arms as an `IN` list
  (`SearchSettings.search_candidate_limit`).
- `search._apply_document_filter(stmt, filter)` — the shared WHERE-clause builder behind
  `find_candidate_documents`, `list_filtered_documents` and `count_filtered_documents`.
  Also gates `raw_text IS NOT NULL`: a document with no parsed text has no metadata to
  match and no chunks to retrieve, so every caller wants that gate, and factoring it here
  is what stops the three callers drifting apart on it.
- `search.list_filtered_documents(session, filter, *, limit, offset, newest_first)` /
  `search.count_filtered_documents(session, filter)` — metadata-only browsing behind
  [`GET /api/documents`](/api/documents.md), with no query text involved.
- `search.get_facets(session)` — the filter vocabulary behind
  [`GET /api/filters`](/api/filters.md); each value list is capped at `MAX_FACET_VALUES`
  (50), most-frequent first.
- `entity.list_entities(session, *, entity_type, name_query, limit, offset)` /
  `entity.count_entities(...)` — an **inner** join through `document_entities` drops
  entities with no documents, since they are dead ends nothing can traverse to. Behind
  [`GET /api/concepts`](/api/concepts.md).
- `document_entity.list_entities_for_document(session, document_id)` — this document's
  entities resolved to name/type, primary relevance sorted first. Behind
  [`GET /api/documents/{id}`](/api/document-detail.md).
- `document_entity.list_documents_for_entity(session, entity_id, *, relevance, limit,
  offset)` / `document_entity.count_documents_for_entity(...)` — the reverse traversal
  hop, behind [`GET /api/concepts/{id}/documents`](/api/concept-documents.md). The first
  caller to filter on `document_entities.relevance` rather than merely storing it.
- `document_reference.list_references_for_document(session, document_id)` — both
  directions of a document's citation graph, each resolved to the other document's
  identity in two queries total (not one per edge). Behind
  [`GET /api/documents/{id}`](/api/document-detail.md).
- `unresolved_reference.get_by_source_document_id(session, document_id)` — this
  document's citations to decisions the corpus does not hold, shown alongside resolved
  references so a reader can tell "cites nothing else" apart from "cites decisions we do
  not hold."
- `session.append_history(session, session_id, entries, last_active_at)` — appends to
  `sessions.history` with one `UPDATE ... SET history = history || :entries::JSONB`,
  never reading the column first. Replaces a read-modify-write that lost whichever of
  two concurrent turns on one session committed second; a missing session is a no-op
  because the `UPDATE` simply matches no row. See [sessions](/data-model/sessions.md).
- `session.list_summaries(session, *, limit, offset)` — the conversation list behind
  [`GET /api/sessions`](/api/sessions.md), projected in SQL so `history` never leaves
  Postgres: `jsonb_extract_path_text(history, '0', 'content')` for the opening question,
  `jsonb_array_length(history)` for the size, and the same expression as the filter that
  keeps sessions which never held a turn out of the list. Paired with
  `session.count_with_history` for the page total.
- `session.delete(session, session_id)` — the only delete in the repository layer that
  a route reaches. Returns whether a row matched, so a delete that removed nothing can
  be a 404 rather than a silent success.

## Protocol-injected namespaces (`repositories/_protocols.py`)

Worker services are handed a repo **namespace** (a module of functions) rather than a
session-bound object, so they can run against either the real SQLAlchemy repositories or
the JSON-file doubles used by `scripts/run_step.py --store fs` (see
[live testing](/playbooks/live-testing.md)). `_protocols.py` declares the structural
interfaces (`DocumentRepo`, `TaskRepo`, `ChunkRepo`, …) that both satisfy.

The Protocol members are declared as read-only `@property` returning a `Callable`, **not**
methods. This is deliberate: a module of module-level functions must satisfy the Protocol,
and both type checkers used here (pyright and ty) agree only on this form — a method-style
member's unbound `self` is not stripped for a module under ty. Only the functions a worker
actually calls are declared (interface segregation); the fs doubles mirror exactly this
surface.

**The new search/browse/traversal repository functions were deliberately not added
here.** `_protocols.py` declares what *workers* call, for the `--store fs` swap and the
worker unit-test seam described below; the [api package](/packages/api.md)'s
search/document/concept services import `shared.repositories.*` modules directly, the
same way every other non-worker call site already does. Extending the Protocols for them
would widen an interface no worker needs and no fs double has to satisfy.

## Why services take repos as parameters (do not "clean this up")

Because repos are plain function modules, a worker *could* just import
`shared.repositories.document` directly. Threading each repo namespace through as a
`process_*` argument is **not** incidental — it is the injection seam, and it buys two
things:

1. **The `--store fs` playground.** Swapping `shared.repositories.*` for
   `scripts/_fsrepos/*` happens purely at the call site. A direct top-level import would
   hard-wire every worker to Postgres.
2. **The unit-test seam.** Tests pass a `MagicMock()` namespace of `AsyncMock`s as the
   repo argument — no import monkeypatching. (This is also why mock call-args are offset
   by one: `session` is always the first positional arg — see
   [testing strategy](/testing.md).)

So the repo parameters are load-bearing. Removing them would silently break both the
`--store fs` chain and the mock-injection strategy; that simplification is only honest if
the playground and mock seam are ever genuinely dropped.

## Async session pattern

```python
from shared.db import get_async_session
from shared.repositories import document as document_repo

async with get_async_session() as session:
    doc = await document_repo.get_by_id(session, doc_id)
```

In FastAPI, `get_async_session` is wrapped in a dependency. In workers, the repo modules
are injected as Protocol-typed namespaces. Integration tests inject the same modules —
the fixtures in `shared.testing.fixtures` return them unchanged — so a test call site
reads exactly like a production one, `session` first.
