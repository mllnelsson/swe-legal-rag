---
type: Concept
title: Worker Architecture Patterns
description: The conventions every subscriber worker shares — the run_pipeline_step task envelope, the subscribe/serve startup split, injected trace scopes, and the commit-before-publish invariant.
tags: [pipeline, workers, task-envelope, patterns]
timestamp: 2026-08-02T00:00:00Z
---

# Worker Architecture Patterns

The conventions shared by every subscriber [pipeline](/pipeline/overview.md) worker.

## Service layer pattern

**All workers are functional** — no service classes. Each worker's orchestration is a
module-level `process_*` async function that takes every dependency as a parameter (repos
as Protocol-typed namespaces, plus session, publisher, config values). No global state.
The `subscribe()` handler closure captures the shared infrastructure objects and passes
them on each call. The repo-parameter threading is the injection seam — see
[repositories](/data-model/repositories.md) for why it is load-bearing.

Anything expensive or fallible to construct is built **once in `subscribe()`, not once
per message**, and threaded in as a parameter: [worker-embed](/pipeline/embed.md) builds
its embedding provider and probes its dimension before subscribing, passing the observed
`expected_dimension` into every `process_embedding()` call rather than re-reading
`shared.config.EMBEDDING_DIMENSION`; [worker-extract](/pipeline/extract.md) builds its
`ExtractionStrategy` once via `create_extraction_strategy()` and passes it into every
`process_extraction()` call, rather than constructing an LLM provider inside the step
body for every document.

## Shared task envelope (`shared.pipeline.run_pipeline_step`)

Every subscriber worker repeats the same task envelope, extracted into
`shared/pipeline.py` so each `process_*` shrinks to "define `body()` (the unique work),
call the runner":

```python
async def run_pipeline_step(
    *, task_repo, session, task_id, document_id,
    next_step: PipelineStep | None,
    queue_publisher: QueuePublisher | None = None,
    body: Callable[[], Awaitable[None]],
    reraise: bool = False,
) -> None: ...
```

The runner:

1. Claims the task; **skips** if missing or already `completed`.
2. Marks `processing` and commits (checkpoint — durable before I/O begins).
3. Runs `body()`.
4. On success: if `next_step` is set, creates the next pending [task](/data-model/tasks.md)
   and publishes it to that step's topic (commit-before-publish), then marks this task
   `completed`. `next_step=None` = terminal step (embed): no publisher needed.
5. On failure, two paths:
   - **`StepInputError`** (raised by `body` for invalid inputs *before* any write —
     missing document / no text): mark `failed`, **no rollback, never re-raise**. An
     expected terminal outcome for that document.
   - **Any other exception:** roll back, mark `failed`, and re-raise only when
     **`reraise=True`**.

`reraise` preserves each worker's propagation behaviour: [chunk](/pipeline/chunk.md) and
[embed](/pipeline/embed.md) re-raise (so the message can be redelivered), the others
swallow. **Crawl is not a pipeline step** — it loops over many listings producing many
documents/tasks, so it keeps its own per-document loop.

## Startup envelope (`shared.worker.subscribe_step` / `serve`)

Every subscriber worker's `__main__.py` splits into two functions: `subscribe()`
builds the worker's wiring (settings, repos, providers) and registers a `handle`
callable against a topic via `shared.worker.subscribe_step`, returning a
`QueueSubscriber` without starting it; `main()` calls `shared.worker.serve(subscriber,
name=...)`, which installs the `SIGTERM`/`SIGINT` handlers and calls
`subscriber.start()`. The split exists because the two have different callers: a worker
process wants both, in that order, but `scripts/run_pipeline.py` composes six workers
into one process by calling only their `subscribe()`s — it wants the registration, not
six competing signal handlers and six blocking `start()` calls.

`subscribe_step(*, topic, queue_settings, handle, scope=None)` owns what
`__main__.py` used to do by hand: it creates the `QueueSubscriber`, and its inner
`handle_message` opens a fresh `AsyncSession` per message (via `get_async_session()`)
and calls `handle(message, session)` inside `asyncio.run()`. `handle` is a worker's
`StepHandler` — a closure over its already-built dependencies — and is threaded into
`run_pipeline_step` and every repo call from there, giving explicit commit control. One
failed message does not roll back others.

## Trace scope injection

`scope`, `subscribe_step`'s other keyword, is a `MessageScope` — a context manager
factory entered around `asyncio.run()`, not inside the coroutine, so a `ContextVar` it
sets is inherited by the loop (`asyncio.Runner` copies the current context when it
builds the loop). `shared` must not depend on `llm-core`, so `shared.worker` cannot
supply a tracing implementation itself; each worker that makes LLM calls passes
`ai.worker_trace_scope(NAME)`, which enters `llm_core.trace_context` keyed on the
message's `document_id`/`task_id` and the worker's own name as `source`. worker-download
and worker-parse make no LLM calls and pass no `scope`. See
[LLM Observability](/observability.md) for the wiring invariant this satisfies.

## Config pattern

Worker-specific settings extend `pydantic_settings.BaseSettings`. Each worker reads its
own env vars alongside the shared `Settings`. `@lru_cache` is used for singleton config
instances.

## Commit-before-publish invariant

All workers call `await session.commit()` before `queue_publisher.publish()`. This
ensures that when `QUEUE_BACKEND=sync` dispatches inline (the subscriber opens a new
session in-process), the committed rows are visible. The same ordering is correct for
Pub/Sub — rows are durable before any async consumer acts on a message.

## Integration test pattern

Integration tests use a real async `Session` on a local Postgres — its own
`overklagan_test` database, never the development one — plus real repo namespaces and
storage, mocked HTTP only, a `SyncQueueBroker` with a recording handler (captures
published messages without triggering downstream workers), and table truncation before
each test.

The fixtures live once in `shared.testing.fixtures`, registered as a pytest plugin by
the repository-root `conftest.py`. They hand back the repo *modules* unchanged, so a
test injects exactly what production injects and calls
`await document_repo.create(session, dto)`. A package's own integration conftest
declares only its `next_topic`.

Rerunning a step means re-driving the same task row —
`shared.testing.pipeline.redrive_task` — because `tasks` holds at most one row per
(document, step) and `run_pipeline_step` skips one already marked completed. See the
[testing strategy](/testing.md).
