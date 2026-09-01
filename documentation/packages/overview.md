---
type: Concept
title: Backend Packages Overview
description: The uv workspace layout, package dependency graph, and the layered Model→Repo→Service→Endpoint architecture.
tags: [backend, packages, workspace, architecture]
timestamp: 2026-09-01T00:00:00Z
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
  ai/                — project-specific LLM logic: Swedish prompts, domain DTOs, synthesis, embeddings
  agents/            — stateless LLM-tool-loop agents; the text-to-SQL agent behind POST /api/sql
                       and the conversational agent behind POST /api/chat
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

`scripts/run_pipeline.py` exists because `QUEUE_BACKEND=sync` publishes into a
module-level broker whose queue only handlers in the *same* process can serve: something
has to subscribe the six downstream handlers before crawl publishes, and something has
to pump the queue afterwards. Each worker's `subscribe()` does the first without
blocking; `serve()` on any one subscriber does the second, since they all front the same
broker. It refuses to run on any other queue backend.

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
agent-kit       ← EXTERNAL pinned git dependency; supplies the agent_kit and agent_kit.llm
                  import namespaces; imports nothing from this repo
ai              ← depends on shared + agent-kit; depended on by api, agents + relevant workers
agents          ← depends on shared + ai + agent-kit; depended on by api
api             ← depends on shared, ai, agents, agent-kit
worker-*        ← depends on shared, some depend on ai; worker-chunk/-extract/-metadata
                  also declare agent-kit
```

`agent-kit` is an **external, standalone dependency** — a pinned git package
(`ssh://git@github.com/mllnelsson/agent-kit.git` at `tag = "v0.1.0"`), not a workspace member.
This repo consumes it through the `agent_kit` namespace (the plan→execute→synthesize
orchestrator, the prompt renderer, the LLM role/provider config, the file trace recorder and
correlation scopes, and the per-conversation context store) and its `agent_kit.llm` layer (the
provider abstraction, the tool loop, `Scratchpad`, and the trace hook). It imports nothing from
this repo; its own internals are documented in the agent-kit repo, not here. `ai` and `agents`
are thin consumers: `ai` keeps the Swedish prompt templates, the evidence DTOs and formatters,
and the embedding abstraction; `agents.run_chat_agent` is a configuration of
`agent_kit.run_agent` plus an event mapping onto the domain's own wire events.

The [ai package](/packages/ai.md) is consumed by [api](/packages/api.md) (decomposition,
synthesis), [agents](/packages/agents.md) (the `TEXT_TO_SQL` prompt and provider role
behind the SQL agent), [worker-metadata](/pipeline/metadata.md) (LLM fallback),
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
