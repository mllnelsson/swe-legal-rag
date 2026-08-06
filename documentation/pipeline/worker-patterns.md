---
type: Concept
title: Worker Architecture Patterns
description: The conventions every subscriber worker shares — the run_pipeline_step task envelope, its per-step progress logging, the subscribe/serve startup split, injected trace scopes, and the commit-before-publish invariant.
tags: [pipeline, workers, task-envelope, patterns, logging]
timestamp: 2026-08-05T12:00:00Z
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

## Progress logging

The envelope also owns **per-step progress logging**, for the same reason it owns the
bookkeeping: every step runs through it, so one place reports every stage at the same
level of detail. A step that logs nothing of its own is still visible in a run.

| Where | Level | Line |
|---|---|---|
| `run_pipeline_step` entry | INFO | `<step>: document <id> started` |
| success | INFO | `<step>: document <id> completed in <n>s -> queued <next>` (or `(final step)`) |
| `StepInputError` | INFO | `<step>: document <id> rejected — <reason>` |
| any other exception | ERROR | `<step>: document <id> failed after <n>s — <error>` (with traceback) |
| already `completed` | INFO | `<step>: document <id> already completed, skipping` |

A worker logs only what is **specific to its own work** on top of that — bytes downloaded,
characters parsed, metadata fields resolved, entities and references extracted, chunks
written, chunks embedded — never a duplicate "starting"/"finished" pair.

Under `QUEUE_BACKEND=sync` the broker adds the one fact the envelope cannot know: queue
depth. `SyncQueueBroker.drain` logs `Queue -> <topic> for document <id> (<n> behind it)`
before each dispatch and a `Queue drained: <n> dispatched, <n> failed, <n> left` summary
at the end, so a long run shows how much is left. `scripts/run_pipeline.py` closes with a
`tasks` count grouped by step and status — see [live testing](/playbooks/live-testing.md).

Formatting is not each entry point's business: `shared.logging_config.configure_logging()`
installs one timestamped root handler and every `main()` calls it **at startup rather than
at import**, so composing workers into one process cannot leave the configuration to
import order.

## Startup envelope (`shared.worker.subscribe_step` / `serve`)

Every subscriber worker's `__main__.py` splits into two functions: `subscribe()`
builds the worker's wiring (settings, repos, providers) and registers a `handle`
callable against a topic via `shared.worker.subscribe_step`, returning a
`QueueSubscriber` without starting it; `main()` calls `shared.worker.serve(subscriber,
name=...)`, which installs the `SIGTERM`/`SIGINT` handlers and calls
`subscriber.start()`. The split exists because the two have different callers: a worker
process wants both, in that order, but `scripts/run_pipeline.py` composes six workers
into one process by calling only their `subscribe()`s — it wants six registrations, not
six competing sets of signal handlers. It serves exactly one subscriber, at the end,
after crawl has filled the queue; every subscriber fronts the same broker, so pumping
one pumps all six.

`subscribe_step(*, topic, queue_settings, handle, scope=None)` owns what
`__main__.py` used to do by hand: it creates the `QueueSubscriber`, and its inner
`handle_message` opens a fresh `AsyncSession` per message (via `get_async_session()`)
and calls `handle(message, session)` inside `asyncio.run()`. `handle` is a worker's
`StepHandler` — a closure over its already-built dependencies — and is threaded into
`run_pipeline_step` and every repo call from there, giving explicit commit control. One
failed message does not roll back others.

**One event loop per message, and it takes the engine with it.** `asyncio.run()` builds a
loop and closes it, and an asyncpg connection cannot outlive the loop that opened it, so
`handle_message` calls `shared.db.dispose_async_engine()` in a `finally` before the loop
goes. Without it the next message inherits a pooled connection whose loop is gone and
fails with `got Future attached to a different loop` — see
[shared](/packages/shared.md). The same obligation falls on anything else that owns a
loop for one unit of work, which is why `worker_crawl.__main__` disposes after its own
`asyncio.run()` too.

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

All workers call `await session.commit()` before `queue_publisher.publish()`. A message
names rows by id, and the step that consumes it always reads them through a session of
its own — a new in-process session under `QUEUE_BACKEND=sync`, another process entirely
under Pub/Sub. Publishing before committing would hand the next step ids it cannot see.

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
