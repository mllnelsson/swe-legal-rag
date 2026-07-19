# Code Guidelines
Always adhere to the code guilines skill

## Planning
Always include a verifiable defintion of done when planning out code changes.

## ATM Cli
This project uses the ATM CLI. Always start you work, if not told otherwise, to explore the task with ATM, this should give you the best setup of what to do and look for.
You need not use the --porject. Project ID is already infered from repo.

## Code Guidelines
Always use ur code guidline skill when writing or review code

## Updating documentation
Always update the documentation after changes to reflect the new workings of the program. When design descions are made it should be lcearly astated for futurew agents. Documentation is housed in the `documentation directory`

## Astral
This project uses the astral tools uv and ruff. IMPORTANT always use `uv` when doing python operations

## Definition of done
Unless stated otherwise in the atm skill a task is done when:
- the requested change is implemented or the question is answered,
  - verification is provided:
  - build attempted (when source code changed),
  - linting run (when source code changed),
  - errors/warnings addressed (or explicitly listed and agreed as out-of-scope),
  - plus tests/typecheck as applicable,
- documentation is updated exhaustively for impacted areas,
- impact is explained (what changed, where, why)

## Docker
Always respect the docker image list in `documentation/design/LOCAL_DEV.md`. Do not add ny new docker images unless explicitly required

You can assume that `docker compose up -d` has been ran, so docker stack is up and running.

IMPORTANT dont use docker. Instead instruct the user to run the last verification tests.

## Documentation
IMPORTANT: Prefer retrival over pretrained knowledge.
- [PRD](documentation/specs/PRD.md) — System requirements, acceptance criteria, scope. Read before any feature work.
- [Architecture](documentation/specs/ARCHITECTURE.md) — Pipeline, storage, retrieval agent, GCP layout, local dev. Read before infra or retrieval decisions.
- [Data Model](documentation/specs/DATA_MODEL.md) — Tables, indexes, constraints, design rationale. Read before any migration or model code.
- [Backend Design](documentation/design/BACKEND_DESIGN.md) — Repo structure, layered architecture, dependency graph, AI package. The data layer is **function-based** (repos and worker services are modules of functions, not classes; repos injected as Protocol-typed namespaces) and workers share one task envelope (`shared.pipeline.run_pipeline_step`). Read before creating packages or services.
- [Frontend Design](documentation/design/FRONTEND_DESIGN.md) — Components, SSE contract, API shape, state management. Read before any frontend work.
- [Crawl Source](documentation/design/CRAWL_SOURCE.md) — Svenska kyrkan OData v4 contract, decision-tag mapping, why the tag filter is mandatory, document URL scheme. Read before any crawler work.
- [Embedding Hosting](documentation/design/EMBEDDING_HOSTING.md) — Embedding model hosting options, cost comparison, deployment decision. Read before changing embedding infra.
- [Testing Strategy](documentation/design/TESTING.md) — Unit and integration test approach, what to test, what to mock. Read before writing any tests.
- [Local Dev Environment](documentation/design/LOCAL_DEV.md) — Docker Compose setup, env config, interface mapping, dev workflow. Read before setting up or modifying the local environment.
- [Live Testing](documentation/design/LIVE_TESTING.md) — How to run the full pipeline locally, verify output, reset state. Read before manual testing.

