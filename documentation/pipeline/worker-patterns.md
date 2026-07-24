---
type: Concept
title: Worker Architecture Patterns
description: The conventions every subscriber worker shares — the run_pipeline_step task envelope, session-per-message, and the commit-before-publish invariant.
tags: [pipeline, workers, task-envelope, patterns]
timestamp: 2026-07-24T00:00:00Z
---

# Worker Architecture Patterns

The conventions shared by every subscriber [pipeline](/pipeline/overview.md) worker.

## Service layer pattern

**All workers are functional** — no service classes. Each worker's orchestration is a
module-level `process_*` async function that takes every dependency as a parameter (repos
as Protocol-typed namespaces, plus session, publisher, config values). No global state.
The `__main__.py` handler closure captures the shared infrastructure objects and passes
them on each call. The repo-parameter threading is the injection seam — see
[repositories](/data-model/repositories.md) for why it is load-bearing.

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

## Session-per-message pattern

Subscriber workers create a new `AsyncSession` for each message (via
`get_async_session()` in `__main__.py`). The session is passed to `process_*()` and
threaded into `run_pipeline_step` and every repo call, giving explicit commit control.
One failed message does not roll back others.

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

Integration tests use a real async `Session` on Docker Postgres, real repo namespaces and
storage (conftest fixtures expose the repo *modules* so they inject exactly as production
does; `shared.testing.bind_repo(module, session)` session-binds a module for direct-call
tests), mocked HTTP only, a `SyncQueueBroker` with a recording handler (captures
published messages without triggering downstream workers), and table truncation before
each test. See the [testing strategy](/testing.md).
