---
type: Concept
title: Backend Packages Overview
description: The uv workspace layout, package dependency graph, and the layered Model→Repo→Service→Endpoint architecture.
tags: [backend, packages, workspace, architecture]
timestamp: 2026-07-27T00:00:00Z
---

# Backend Packages Overview

## Tooling

- **uv** — package management and workspace orchestration
- **FastAPI** — API framework
- **SQLAlchemy** — ORM
- **Alembic** — database migrations
- **Pydantic** — DTOs and request/response models

## Repo structure (uv workspace)

Monorepo with a package per concern; shared code and AI tooling are internal packages.

```
packages/
  shared/            — SQLAlchemy models, Pydantic DTOs, repo layer, DB config, common utils
  llm-core/          — standalone, project-agnostic LLM abstraction
  ai/                — project-specific LLM logic: prompts, domain DTOs, decomposition, synthesis, embeddings
  api/               — FastAPI app, endpoints, retrieval service layer
  worker-crawl/  worker-download/  worker-parse/  worker-metadata/
  worker-extract/  worker-chunk/  worker-embed/
alembic/             — migration scripts (runs against shared.db.Base metadata)
alembic.ini          — Alembic config (sqlalchemy.url via DATABASE_URL in env.py)
scripts/
  run_pipeline.py    — crawl→embed in one process; the entrypoint the pipeline container runs
  run_step.py        — one step, one document, no cascade; the hand-testing runner
Dockerfile           — optional container image for the whole backend (python:3.12-slim + uv sync)
docker-compose.yml   — optional; Postgres+pgvector default, pipeline+api under "app", MinIO+Redis under "full"
docker/init.sql      — enables the pgvector extension; redundant, migration 001 does it too
```

`scripts/run_pipeline.py` exists because `QUEUE_BACKEND=sync` dispatches into a
module-level broker in the *same* process: something has to subscribe the six downstream
handlers before crawl publishes, and each worker's `main()` already does exactly that and
returns (`SyncQueueSubscriber.start()` is a no-op). Composing them is calling them in
order. It refuses to run on any other queue backend.

The same script is the `pipeline` compose service's command, and `api` runs uvicorn from
the same image — one image, two services, and deliberately **one** pipeline container
rather than seven, for the same in-process-broker reason. See
[Running in Containers](/playbooks/local-dev.md#running-in-containers). Each worker
remains its own deployable unit for Cloud Run, which needs a real queue backend first.

All packages use src layout (`packages/<name>/src/<python_name>/`) with `py.typed`
markers; hyphenated directory names map to underscore Python names (`worker-crawl` →
`worker_crawl`). Each worker is its own deployable Cloud Run unit with its own
`pyproject.toml`, depending on `shared`.

## Package dependency graph

```
shared          ← depended on by everything
llm-core        ← standalone; depends only on pydantic, pydantic-settings, google-genai, openai
ai              ← depends on shared + llm-core; depended on by api + relevant workers
api             ← depends on shared, ai
worker-*        ← depends on shared, some depend on ai
```

The [ai package](/packages/ai.md) is consumed by [api](/packages/api.md) (decomposition,
synthesis), [worker-metadata](/pipeline/metadata.md) (LLM fallback),
[worker-extract](/pipeline/extract.md) (entities & references),
[worker-chunk](/pipeline/chunk.md) (summaries), and [worker-embed](/pipeline/embed.md)
(embeddings).

## Layered architecture

```
Model (SQLAlchemy)  →  Repo (queries + ORM→DTO mapping)  →  Service (business logic)  →  Endpoint (HTTP concerns)
```

- **Model:** SQLAlchemy table definitions; lives in `shared`. Single source of truth for
  schema — Alembic generates migrations from these.
- **Repo:** query logic only, as [modules of async functions](/data-model/repositories.md)
  (not classes). Every function takes an `AsyncSession` first and takes/returns DTOs —
  never leaks ORM objects. Lives in `shared`.
- **Service:** business and domain logic; orchestrates repos, calls `ai`, handles
  pipeline logic. Lives in the respective package (`api` or worker). Workers wrap their
  unique work in the [shared task envelope](/pipeline/worker-patterns.md).
- **Endpoint:** request parsing, response formatting, HTTP status codes. Thin. Lives in
  `api`. Workers skip this layer — they consume from Pub/Sub directly into the service
  layer.

## Design principles

- **Interface abstraction everywhere** — LLM provider, embedding model, storage backend,
  queue are all swappable via config for local dev and future flexibility.
- **DTOs as boundaries** — Pydantic models define the contract between layers; ORM
  objects never cross the repo boundary.
- **Workers are thin** — each worker's service layer does one thing; complexity lives in
  `shared` and `ai`.
- **Config over code** — model selection, provider keys, DB connection, queue config are
  all environment-driven.
