---
type: Concept
title: Testing Strategy
description: The backend's two-level (unit + integration) testing approach — what to test, what to mock, how the split is enforced, the separate database integration tests run against — plus the frontend suite and the two tests that check the contract across the language boundary.
tags: [testing, pytest, strategy]
timestamp: 2026-08-16T00:00:00Z
---

# Testing Strategy

## Tooling

- **pytest** — test runner for all levels
- **pytest-asyncio** — async test support, in `asyncio_mode = "auto"`: an `async def`
  test needs no `@pytest.mark.asyncio` decorator
- **respx** — httpx transport-level mocking, for code that talks HTTP
  (`worker-crawl`'s OData client)

## Two Levels

**Unit tests** — isolate the logic you wrote. Mock external dependencies at the
interface boundaries defined in [`shared`](/packages/shared.md) and
[`ai`](/packages/ai.md). Fast, no I/O.

**Integration tests** — exercise a full module top-to-bottom against a real local
Postgres and the local filesystem. Validate wiring, not just logic.

**The split is enforced by directory, not by decorator.** The repository-root
`conftest.py` marks every test under a `tests/integration/` directory `integration`
during collection, so placement is the whole contract — a new file cannot forget the
marker and slip into the default run. Do not add `@pytest.mark.integration` by hand;
it is redundant.

`addopts` in `pyproject.toml` carries `-m "not integration"`, so **a bare
`uv run pytest` is unit-only**. That is deliberate: integration tests need a database
and truncate every table in it, so running them is an explicit act. See
[running tests](#running-tests).

## What to Test

Test logic you control: service orchestration, query construction, response parsing,
error handling, data transformations, prompt construction, DTO mapping, filtering
logic.

Do **not** test: dataclass/Pydantic model initialization, ORM model field
declarations, third-party library behavior, trivial getters/setters, config loading
mechanics. If the test would break only because a dependency changed its API — it's not
your test to write.

Concretely, these all failed that rule and are gone:

| Shape | Why it is not a test |
|---|---|
| `assert Frozen(a=1).a == 1`, `pytest.raises(FrozenInstanceError)` | `@dataclass` generated it |
| `SomeEnum.LOCAL == "local"` | `StrEnum` semantics. Pin wire strings where they hit the wire — in the provider mapping tests |
| `Dto.model_validate(namespace)` copies fields | pydantic's `from_attributes` |
| `get_settings() is get_settings()` | `functools.lru_cache` |
| `engine.pool._pre_ping is True` | a **private** SQLAlchemy attribute. Deliberate settings belong in a comment at the call site |
| `session.execute.assert_called_once()` as the only assertion | passes just as happily if the `WHERE` clause was never built. Assert the filter against real Postgres instead |
| `result is mock_cls.return_value` | the patch returned its own canned value |
| `isinstance(provider, SomeProtocol)` | `runtime_checkable` only checks method *names* |

A unit test also must not name a heavyweight optional dependency as a patch target.
`mock.patch` resolves its target eagerly, so `patch("sentence_transformers.…")`
*imports* sentence-transformers — and with it torch — into a suite that is meant to be
fast and offline. Patch a seam you own (`LocalEmbeddingProvider._get_model`), or put a
stub module in `sys.modules` when the guard being tested is the import itself.

A third way to dodge the same problem, used by `ai.tokenization`: hand the consumer a
**value carrying the callable** rather than a Protocol with an implementation behind it.
`EmbeddingRuler.count_tokens` is a plain `Callable[[str], int]`, so a test double is a
lambda (or, in the [chunk](/pipeline/chunk.md)/[embed](/pipeline/embed.md) pipeline
integration suites, a word counter) — there is nothing to patch, and `transformers`
(which would pull in torch the same way sentence-transformers does) never has to import
in a suite that needs to stay fast and offline. Both new integration tests keep the word
counter deliberately, so the suite needs no HuggingFace hub access or a warm tokenizer
cache to run.

**Regex-based parsers must be tested against observed corpus variants, not one idealised
spelling.** `shared.segmentation` and `worker-extract`'s rule-based extractor both had
fixtures that used the *minority* spelling for the exact thing that later turned out
broken: on the 25-document sample the corpus stood at on 2026-08-04, the appendix-label
test used `Bilaga A` while 22 of 25 real decisions wrote `BILAGA A`, and the
kyrkoordningen fixture used `kyrkoordningen kapitel 32 § 5`, a phrasing that occurred
**zero** times in that sample, while the majority form (`58 kap. 1 § kyrkoordningen`,
lagrum before the statute's name) occurred 213 times and matched nothing. Both defects
were invisible to their own test suites for exactly that
reason — the fixture and the code agreed with each other, just not with the documents. A
parser test suite for this pipeline should pin every spelling variant known to occur in
`data/store/documents.json` (or a representative sample of it), not just the one that was
easiest to write down. See [structural fields are parsed, not
inferred](/decisions/structural-fields-are-parsed.md) for why these fields are worth
getting right with rules rather than delegating them to an LLM.

## Unit Tests

Every package gets unit tests. Mock at the interface boundary — the abstractions in
`shared` and `ai` are the seam.

**What to mock:**
- Database → mock the repo layer. [Repos](/data-model/repositories.md) are **modules of
  functions** injected as Protocol-typed namespaces (`DocumentRepo`, `TaskRepo`, …), so
  mock by passing a `MagicMock()` namespace whose functions are `AsyncMock`s returning
  canned DTOs. Every repo function takes `session` as its first argument, so mock
  call-args are offset by one (e.g. the DTO is `call_args[0][2]`, not `[0][1]`).
- LLM/embeddings → mock the `ai` interfaces (return canned responses)
- GCS/storage → mock the storage interface
- Pub/Sub/queue → mock the queue interface

**LLM/embedding provider unit tests never make live calls.** `GeminiProvider` tests
mock the `google-genai` SDK client (`test_gemini_mapping.py`); `OpenAiCompatibleProvider`
and `OpenAiCompatibleEmbeddingProvider` tests mock `openai.AsyncOpenAI` the same way
(`test_openai_compatible_mapping.py`, `test_openai_compatible_embedding_provider.py`) —
construct the provider, then patch `llm_core._clients.get_async_openai` (each module
imports it by name, so patch it at the accessor in that module, e.g.
`_openai_compatible.get_async_openai`) to return a `MagicMock()`, and assert on the
mapped request/response shape. There is no `provider._client` to replace: a provider
looks its client up per call, bound to the running loop, rather than holding one built
at construction — see [loop-bound
clients](/packages/llm-core.md#loop-bound-clients-_clientspy). Real API calls to Berget
or Gemini never happen in unit tests. Composition roots that construct real providers at
startup (`api/main.py`'s `_lifespan`, worker `__main__.py`/factory functions) need a
dummy `BERGET_API_KEY` in the test environment for construction to succeed — see the
`_berget_api_key` autouse fixture in `packages/api/tests/unit/conftest.py` and
`packages/worker-extract/tests/unit/conftest.py`. Constructing a provider makes no
network calls by itself; only an actual `.generate()`/`.embed()` call would, and those
call sites are the ones under test/mocked.

**What to assert:**
- Your service logic given known inputs from mocks
- Correct arguments passed to mocked dependencies
- Error paths: what happens when the LLM returns garbage, the DB is empty, the PDF is
  malformed
- Prompt construction: assert the right context, filters, and chunks are assembled —
  don't assert on LLM output

**Per-layer guidance:**
- Repo layer: test query construction and ORM→DTO mapping against a mock session
  (functions take `session` first). Not worth testing simple passthrough queries.
- Service layer: the bulk of unit tests live here. Mock repo namespaces and `ai`
  interfaces, test the orchestration logic. Worker `process_*` bodies run inside
  `shared.pipeline.run_pipeline_step`, so assert on the status transitions
  (`processing` → `completed`/`failed`) and the published next-topic message.
- Endpoint layer: test request validation, HTTP status codes, error response shapes.
  Thin layer, thin tests.
- AI package: test prompt rendering via the `render(template, context)` function,
  response parsing, retry/fallback logic. Mock the provider HTTP calls.

<a id="no-init-py"></a>

> **`tests/` directories have no `__init__.py`.** With `--import-mode=importlib`, an
> `__init__.py` in `tests/unit/` or `tests/integration/` makes pytest derive the
> module's dotted name from that package chain (e.g. `tests.integration.conftest`) —
> identical across every package, since none of them share a common parent package. That
> caused two failure modes: conftest.py collisions ("Plugin already registered under a
> different name") when running the full testpaths glob, and silent shadowing of
> duplicate test-file basenames (`test_service.py`, `test_config.py`) where only one of
> several identically-named files got collected. Without `__init__.py`, pytest falls
> back to a full-path-derived unique module name, so the aggregate run from the repo
> root collects every file correctly. Don't add `__init__.py` back to these directories.

## Integration Tests

One level up. Exercise a full module's service layer with real local dependencies.

### The test database

**Integration tests never run against the development database.** They truncate every
table before each test, so pointing them at `overklagan` would destroy whatever the
pipeline has crawled. The target is resolved in
`shared.testing.database.resolve_test_database_url`:

1. `TEST_DATABASE_URL` when set — the explicit escape hatch, for CI.
2. Otherwise derived from `DATABASE_URL` by appending `_test` to the database name, so
   the usual setup needs no configuration at all.
3. If the result names the same database as `DATABASE_URL`, **collection aborts** with
   a message naming both and the `createdb` command to fix it. This guard fails
   closed — a misconfiguration ends the run before a single table is touched.

**Setup:**
- A Postgres with pgvector — the Homebrew install from
  [local dev](/playbooks/local-dev.md). The fixtures do not care how the server got
  there
- The test database itself: `createdb -O postgres overklagan_test`. Full per-platform
  steps, including the Docker Compose path, are in [local dev](/playbooks/local-dev.md)
- Local filesystem for storage (no MinIO needed at this level)
- Real `ai` interfaces with recorded fixtures or a cheap live model call where cost is
  negligible

Nothing else: the `db_engine` fixture migrates the test database itself on first use.

### Schema comes from alembic

The session-scoped `db_engine` fixture runs `alembic upgrade head`, not
`Base.metadata.create_all()`, so tests see the schema production has — including what
migrations *alter* after creating it, and the `CREATE EXTENSION vector` that
`create_all` never issues.

`alembic/env.py` builds its engine from `shared.db.get_engine()`, which reads
`DATABASE_URL` through a cached settings object, so a caller cannot redirect it by
passing a URL. It accepts an override instead — `config.attributes["db_url"]`
programmatically, or on the command line:

```bash
uv run alembic -x db_url=postgresql://postgres:postgres@localhost:5432/overklagan_test upgrade head
```

### Shared fixtures

The database plumbing lives once, in `shared.testing.fixtures`, registered globally as
a pytest plugin by the root `conftest.py`. It provides `test_database_url`, `db_engine`,
`clean_database`, `session`, every repo fixture, `local_storage`, `published_messages`
and `sync_publisher`.

A package's `tests/integration/conftest.py` declares only what is genuinely local to it
— usually just the `next_topic` fixture naming the step it hands off to, which
`sync_publisher` registers a recording handler for.

**Repo fixtures hand back the repository module unchanged**, so a test calls exactly
what a worker calls: `await document_repo.create(session, dto)`. There is one
convention, matching production; see [repositories](/data-model/repositories.md).

**Per-module examples:**
- [`worker-parse`](/pipeline/parse.md): feed a real PDF path → assert raw text
  extracted, document row updated
- [`worker-metadata`](/pipeline/metadata.md): feed a parsed document → assert metadata
  fields populated correctly
- [`worker-extract`](/pipeline/extract.md): feed a document with raw text → assert
  entities and references created
- [`worker-chunk`](/pipeline/chunk.md): feed a document → assert chunks created with
  contextual text, summary stored
- [`worker-embed`](/pipeline/embed.md): feed chunks → assert embeddings written, correct
  dimensionality
- [`agents`](/packages/agents.md): run model-authored SQL through the real read-only
  sandbox → assert a write is refused by the transaction itself (not just the static
  guard), and that a failed statement leaves the session usable for the request that
  follows
- [`api`](/packages/api.md): send a chat request → assert query decomposition runs,
  retrieval returns results, SSE stream produces expected event shapes

**Database state:** the `session` fixture truncates every table before each test, so a
test starts empty and inserts the rows it needs. No shared state between tests.

**Rerunning a step is not creating a second task.** `tasks` holds at most one row per
(document, step), and [`run_pipeline_step`](/pipeline/worker-patterns.md) skips a task
it finds already completed. A test that models a rerun has to re-drive the same row —
`shared.testing.pipeline.redrive_task(session, task_repo, task_id)` — not create
another one, which violates `uq_tasks_document_id_step`.

## What Not to Mock

Don't mock what you don't own in the wrong direction. Specifically: don't write unit
tests that assert on the shape of a mocked LLM response you invented. That tests your
imagination, not your code. If you need to verify behavior with a real LLM response
shape, that's an integration test with a recorded fixture.

## Test Location

Tests live alongside their package, split into `unit/` and `integration/`:

```
packages/
  shared/
    tests/
      unit/
      integration/
  ai/
    tests/
      unit/          # no integration/ — this package has no database of its own
  api/
    tests/
      unit/
      integration/
  worker-parse/
    tests/
      unit/
      integration/
  ...
scripts/
  tests/
    unit/            # the filesystem-backed repo stand-ins behind run_step.py
```

The directory name is load-bearing: `tests/integration/` is what earns the marker.

**A new package's tests must be added to `testpaths` in `pyproject.toml`** or they are
never collected — the list is explicit, not a glob. `scripts/tests` sat outside it for a
while, and its eight tests silently never ran.

`tests/` directories have no `__init__.py` — see [the note below](#no-init-py).

## Running Tests

```bash
# Unit tests — the default. Fast, hermetic, needs no infrastructure.
uv run pytest

# Integration tests alone. Needs Postgres and the overklagan_test database.
uv run pytest -m integration

# Everything.
uv run pytest -m ""

# One package, or one file.
uv run pytest packages/api/tests/
uv run pytest packages/api/tests/unit/test_chat_route.py
```

A `-m` on the command line overrides the one in `addopts`, which is what makes
`-m integration` and `-m ""` work.

**Agents and scripted runs should use the bare `uv run pytest`.** It cannot reach a
database, so it cannot destroy one.

## Frontend

Everything above is the Python backend. The [frontend](/frontend/overview.md) has its
own suite: 9 Vitest files under `frontend/src/**/*.test.ts{,x}`, run from `frontend/`
with `npm test` (`vitest run`) or watched with `npm run test:watch`.

**Tooling:** Vitest + Testing Library + jsdom. Global setup lives in
`frontend/src/test-setup.ts` (jest-dom matchers, `cleanup` after each test, a
`scrollIntoView` stub jsdom does not implement). Shared fixtures live in
`frontend/src/test/factories.ts` — not stand-ins for the API, since the app talks to
the live API at runtime, but one-field-at-a-time test data typed off the generated
`schema.d.ts` (see [generated types](/frontend/generated-types.md)), so a backend
contract change breaks a fixture at compile time rather than letting a test pass
against a shape the API no longer returns.

### The two load-bearing cross-boundary tests

Most of the suite is ordinary component/hook testing. Two files are not, and are the
real reason this section belongs in a testing *strategy* doc rather than only in the
frontend's own concept page:

- **`features/agent/progress-labels.test.ts`** `?raw`-imports
  `packages/agents/src/agents/chat/_dtos.py` and parses `ProgressLabel` out of the
  Python source as text, then asserts the client has a Swedish word for every label
  the API can emit. A label added on the backend with no matching entry in
  `progress-text.ts` fails this test — and therefore the frontend build — instead of
  reaching a reader as a raw key like `decision.audit`. This cross-language import is
  why `vitest.config.ts` sets `server.fs.allow: [".."]`: Vite refuses by default to
  serve a file outside the project root it is configured against.
- **The two honesty-rule suites** (`src/components/research/honesty-rules.test.tsx`,
  `src/features/agent/agent-honesty-rules.test.tsx`) are the tested form of [the
  honesty rules](/frontend/honesty-rules.md) — one test per rule, asserting the claim
  the UI is and is not allowed to make about a search result or an agent-written
  answer.

### Why this matters more here than in a typical SPA

`src/api/chat-events.ts` — the SSE event contract for [`POST
/api/chat`](/api/chat-endpoint.md) — is hand-maintained, not generated: a
`StreamingResponse` publishes nothing to OpenAPI, so there is no schema for
`openapi-typescript` to read (see [generated types](/frontend/generated-types.md)).
For that one contract, `chat-stream.test.ts` and the agent-mode test files are the
**only** check that exists that the client's understanding of the SSE frames still
matches the backend's. Everything else the frontend depends on is compiler-checked
against the generated `schema.d.ts`, with no equivalent test required to catch drift.
