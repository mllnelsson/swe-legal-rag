---
type: Repository
title: Repository Layer
description: The function-based data-access layer bridging SQLAlchemy models and Pydantic DTOs, injected into services as Protocol-typed namespaces.
resource: packages/shared/src/shared/repositories
tags: [data-model, repositories, data-layer, dto, protocol]
timestamp: 2026-08-01T00:00:00Z
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
- `document.get_by_case_number` — lookup by `case_number`
- `task.update_status` — sets `started_at` on `processing`, `completed_at` on
  `completed`/`failed` (compared against `TaskStatus` members)
- `entity.upsert` — check-then-insert on the `(name, type)` unique constraint
- `document_entity.upsert` — check-then-insert; upgrades `mentioned` → `primary`
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
- `search.find_candidate_documents(session, filter)` — narrows the corpus via metadata
  WHERE, EXISTS subqueries through `document_entities`→`entities`, and
  `document_references` traversal in both directions; an empty filter returns all
  document IDs with `raw_text`

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
