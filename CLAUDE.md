# Code Guidelines
Always adhere to the code guilines skill

## Planning
Always include a verifiable defintion of done when planning out code changes.

## ATM Cli
Do not use ATM for this repo, it is currently disabled
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
  - plus tests/typecheck as applicable. `uv run pytest` is the test command: it
    runs unit tests only and needs no infrastructure. Integration tests are
    opt-in — `uv run pytest -m integration` — and need Postgres plus the
    `overklagan_test` database. Do not run them unless asked.
- documentation is updated exhaustively for impacted areas,
- impact is explained (what changed, where, why)

## Project state
Nothing is deployed and no corpus has been ingested — see
[deployment state](documentation/reference/deployment-state.md). Breaking changes,
schema recreation and embedding-model changes are all free right now. Do not plan
around migrations, re-embeds or deployed consumers unless that doc says otherwise.

## Local database
Assume Postgres + pgvector is already running on `localhost:5432` with the schema
migrated — `DATABASE_URL` in `.env` works as shipped. Integration tests use a
*second* database, `overklagan_test`, which they truncate; it is derived from
`DATABASE_URL` and needs one `createdb`. How it got there is
platform-dependent (Docker Compose on Linux, native Homebrew on macOS); the setup, the
per-platform differences and the troubleshooting table live in
[local dev](documentation/playbooks/local-dev.md). Read it before touching local DB
setup — don't assume one platform's path.

`overklagan` is **read-only to you**. It holds locally crawled data that re-running
the pipeline does not reproduce. Your writable copy is `overklagan_coding_agent`,
which `DATABASE_URL` and `PGDATABASE` already point at; `.claude/hooks/db-guard.sh`
refuses any Bash command that would write elsewhere, and reads against `overklagan`
are fine. A change that genuinely has to land in `overklagan` is the user's call, not
something to work around.

**Never run `.claude/hooks/db-sandbox.sh refresh --yes` on your own initiative — ask
first.** One Postgres cluster serves every worktree, so there is exactly one sandbox,
shared with every other session and agent working on this checkout; refreshing drops
it and takes their work with it. The `--yes` is what makes that a deliberate choice,
and the choice is the user's. Session start runs `ensure`, which only creates the
sandbox when it is *missing* and never drops one — so **a stale sandbox is normal**,
not a bug: it can be a schema change and a whole corpus behind `overklagan`. Check
`select count(*) from chunks` in both before trusting it, and if you only need to
*read* real data, read `overklagan` — that costs nobody their sandbox. See
[refreshing the sandbox](documentation/playbooks/local-dev.md).

## Docker
Always respect the docker image list in `documentation/playbooks/local-dev.md`. Do not add ny new docker images unless explicitly required

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
- [Local Dev Environment](documentation/playbooks/local-dev.md) — native Homebrew Postgres setup, env config, interface mapping, dev workflow, and the optional container path. Read before setting up or modifying the local environment.
- [Live Testing](documentation/playbooks/live-testing.md) — How to run the full pipeline locally, verify output, reset state. Read before manual testing.

