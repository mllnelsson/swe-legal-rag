# Testing Strategy: Överklagandenämnden Decision Search Tool

## Tooling

- **pytest** — test runner for all levels
- **pytest-asyncio** — async test support (FastAPI, async service calls)

## Two Levels

**Unit tests** — isolate the logic you wrote. Mock external dependencies at the interface boundaries defined in `shared` and `ai`. Fast, no I/O.

**Integration tests** — exercise a full module top-to-bottom. Use real local replacements (Docker Postgres, local filesystem). Validate wiring, not just logic.

## What to Test

Test logic you control: service orchestration, query construction, response parsing, error handling, data transformations, prompt construction, DTO mapping, filtering logic.

Do **not** test: dataclass/Pydantic model initialization, ORM model field declarations, third-party library behavior, trivial getters/setters, config loading mechanics. If the test would break only because a dependency changed its API — it's not your test to write.

## Unit Tests

Every package gets unit tests. Mock at the interface boundary — the abstractions in `shared` and `ai` are the seam.

**What to mock:**
- Database → mock the repo layer. Repos are **modules of functions** injected as Protocol-typed namespaces (`DocumentRepo`, `TaskRepo`, …), so mock by passing a `MagicMock()` namespace whose functions are `AsyncMock`s returning canned DTOs. Every repo function takes `session` as its first argument, so mock call-args are offset by one (e.g. the DTO is `call_args[0][2]`, not `[0][1]`).
- LLM/embeddings → mock the `ai` interfaces (return canned responses)
- GCS/storage → mock the storage interface
- Pub/Sub/queue → mock the queue interface

**What to assert:**
- Your service logic given known inputs from mocks
- Correct arguments passed to mocked dependencies
- Error paths: what happens when the LLM returns garbage, the DB is empty, the PDF is malformed
- Prompt construction: assert the right context, filters, and chunks are assembled — don't assert on LLM output

**Per-layer guidance:**
- Repo layer: test query construction and ORM→DTO mapping against a mock session (functions take `session` first). Not worth testing simple passthrough queries.
- Service layer: the bulk of unit tests live here. Mock repo namespaces and `ai` interfaces, test the orchestration logic. Worker `process_*` bodies run inside `shared.pipeline.run_pipeline_step`, so assert on the status transitions (`processing` → `completed`/`failed`) and the published next-topic message.
- Endpoint layer: test request validation, HTTP status codes, error response shapes. Thin layer, thin tests.
- AI package: test prompt rendering via the `render(template, context)` function, response parsing, retry/fallback logic. Mock the provider HTTP calls.

> **`tests/` directories have no `__init__.py`.** With `--import-mode=importlib`, an `__init__.py` in `tests/unit/` or `tests/integration/` makes pytest derive the module's dotted name from that package chain (e.g. `tests.integration.conftest`) — identical across every package, since none of them share a common parent package. That caused two failure modes: conftest.py collisions ("Plugin already registered under a different name") when running the full testpaths glob, and silent shadowing of duplicate test-file basenames (`test_service.py`, `test_config.py`) where only one of several identically-named files got collected. Without `__init__.py`, pytest falls back to a full-path-derived unique module name, so the aggregate run (`uv run pytest` from repo root, or `uv run pytest -m "not integration"` to skip the DB-backed tests) collects every file correctly. Don't add `__init__.py` back to these directories.

## Integration Tests

One level up. Exercise a full module's service layer with real local dependencies.

**Setup:**
- Docker Postgres with pgvector (same `ankane/pgvector` image as local dev)
- Local filesystem for storage (no MinIO needed at this level)
- Real `ai` interfaces with recorded fixtures or a cheap live model call where cost is negligible

**Per-module examples:**
- `worker-parse`: feed a real PDF path → assert raw text extracted, document row updated
- `worker-metadata`: feed a parsed document → assert metadata fields populated correctly
- `worker-extract`: feed a document with raw text → assert entities and references created
- `worker-chunk`: feed a document → assert chunks created with contextual text, summary stored
- `worker-embed`: feed chunks → assert embeddings written, correct dimensionality
- `api`: send a chat request → assert query decomposition runs, retrieval returns results, SSE stream produces expected event shapes

**Database state:** each integration test manages its own data — insert setup rows, run the service, assert outcomes, clean up. No shared test database state between tests.

## What Not to Mock

Don't mock what you don't own in the wrong direction. Specifically: don't write unit tests that assert on the shape of a mocked LLM response you invented. That tests your imagination, not your code. If you need to verify behavior with a real LLM response shape, that's an integration test with a recorded fixture.

## Test Location

Tests live alongside their package:

```
packages/
  shared/
    tests/
      unit/
      integration/
  ai/
    tests/
      unit/
      integration/
  api/
    tests/
      unit/
      integration/
  worker-parse/
    tests/
      unit/
      integration/
  ...
```

## Running Tests

```bash
# All unit tests (fast, no infra needed)
uv run pytest -m "not integration"

# Everything, including integration tests (requires Docker Postgres running)
uv run pytest

# Single package
uv run pytest packages/api/tests/
```
