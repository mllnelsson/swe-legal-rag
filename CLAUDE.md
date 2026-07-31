# Code Guidelines
Always adhere to the code guilines skill

## Planning
Always include a verifiable defintion of done when planning out code changes.

## ATM Cli
This project uses the ATM CLI. Always start you work, if not told otherwise, to explore the task with ATM, this should give you the best setup of what to do and look for.
You need not use the --porject. Project ID is already infered from repo.

## Code Guidelines
Always use ur code guidline skill when writing or review code

## Astral
This project uses the astral tools uv and ruff. IMPORTANT always use `uv` when doing python operations
## Python

- Style is ruff-enforced but **not** auto-applied — nothing formats your
  code after you write it. Write it already-formatted.
- `ty` type-checks the whole project when a turn ends. Annotate as you go;
  don't leave inference to be discovered at the end.
- Lint findings surfaced mid-turn are advisory. Fix what's real, and skip
  nits in code you didn't touch.

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
Always respect the docker image list in `documentation/playbooks/local-dev.md`. Do not add ny new docker images unless explicitly required

You can assume that `docker compose up -d` has been ran, so docker stack is up and running.

IMPORTANT dont use docker. Instead instruct the user to run the last verification tests.

## Documentation
IMPORTANT: Prefer retrival over pretrained knowledge.

`documentation/` is an OKF bundle: markdown concepts with YAML frontmatter.
When delegating any docs lookup to Explore, include in the prompt:
"Links beginning with `/` are relative to documentation/, not the filesystem.
Read YAML frontmatter (`description`, `type`) before opening bodies."
Documentation is an OKF v0.1 knowledge bundle rooted at `documentation/` — one concept
per file, each with YAML frontmatter and `/`-absolute cross-links. Start at
[documentation/index.md](documentation/index.md) for the full map. Always follow the
`okf-docs` skill when reading or editing any file under the bundle.
Use the `òkf-docs-writer` agents when handleing the documentation.

Key entry points:
- [PRD](documentation/prd.md) — System requirements, acceptance criteria, scope. Read before any feature work.
- [Architecture Overview](documentation/architecture.md) — Subsystems, storage layer, and pointers into the pipeline/retrieval/packages sections. Read before infra or retrieval decisions.
- [Data Model](documentation/data-model/) — One concept per table, plus [indexes](documentation/data-model/indexes.md), [design notes](documentation/data-model/design-notes.md), and the [repository layer](documentation/data-model/repositories.md). Read before any migration or model code.
- [Backend Packages](documentation/packages/) — Repo structure, layered architecture, dependency graph, and the shared/llm-core/ai/api packages. The data layer is **function-based** (repos and worker services are modules of functions, not classes; repos injected as Protocol-typed namespaces) and workers share one task envelope (`shared.pipeline.run_pipeline_step`). Read before creating packages or services.
- [Ingestion Pipeline](documentation/pipeline/overview.md) — The seven worker Service concepts and [worker patterns](documentation/pipeline/worker-patterns.md). Read before any worker work.
- [Frontend](documentation/frontend/overview.md) and the [Chat Endpoint contract](documentation/api/chat-endpoint.md) — Read before any frontend or SSE work.
- [Crawl Source](documentation/reference/crawl-source.md) — Svenska kyrkan OData v4 contract, decision-tag mapping, document URL scheme; the mandatory [tag filter](documentation/decisions/tag-filter.md). Read before any crawler work.
- [Decisions](documentation/decisions/) — Embedding [model](documentation/decisions/embedding-model.md)/[hosting](documentation/decisions/embedding-hosting.md)/[dimension](documentation/decisions/embedding-dimension.md) and the [architectural register](documentation/decisions/architectural-register.md). Read before changing embedding infra or system-shaping choices.
- [LLM Observability](documentation/observability.md) — Every LLM/embedding call is traced to file storage with full prompt, response and tokens; cost is deliberately not computed — records carry `model` and `usage`, and pricing is an analysis step. **Wiring invariant: every process making LLM calls must call `install_file_tracing()` once at startup and set `trace_context` at each unit-of-work boundary.** Read before touching any LLM call site or adding a process that makes one.
- [Testing Strategy](documentation/testing.md) — Unit and integration test approach, what to test, what to mock. Read before writing any tests.
- [Local Dev Environment](documentation/playbooks/local-dev.md) — Docker Compose setup, env config, interface mapping, dev workflow. Read before setting up or modifying the local environment.
- [Live Testing](documentation/playbooks/live-testing.md) — How to run the full pipeline locally, verify output, reset state. Read before manual testing.

