"""Runs the whole ingestion pipeline — crawl through embed — in one process.

Why this exists: with ``QUEUE_BACKEND=sync`` a publish only reaches a handler
subscribed *in the same process*, and the broker backing it
(``shared.queue.factory``) is a module-level singleton. A handler registered in
another process is therefore invisible, which is why ``python -m worker_crawl``
on its own fails with ``QueueHandlerError: No handler registered for topic:
'download'`` — nothing ever subscribed.

The fix is to register the six downstream handlers first, run crawl, and then
pump the queue crawl filled. Each worker exposes ``subscribe()`` for exactly
this: it builds the worker's wiring, registers its handler and returns without
blocking. Publishing appends to the shared broker rather than calling a handler
inline (see ``shared/queue/sync.py``), so nothing downstream runs until the
pump starts — which is what makes the whole run happen outside any event loop,
leaving each step free to open its own.

This is what the ``pipeline`` container runs — see /playbooks/local-dev.md.
For iterating on one step at a time instead, use ``scripts/run_step.py``.

A run also re-drives anything a previous run left ``pending``, because crawl
publishes only for documents it has just discovered: a document stranded
mid-pipeline is already in ``documents``, so the next crawl skips it and its
pending task is a message nobody would ever send. Pass ``--no-resume`` to crawl
only.

Usage (from the repo root, with .env configured):

    uv run python scripts/run_pipeline.py                    # current year
    uv run python scripts/run_pipeline.py --years all        # full backfill
    uv run python scripts/run_pipeline.py --years 2019-2021  # a range
    uv run python scripts/run_pipeline.py --no-resume        # skip pending work
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from collections.abc import Callable

from dotenv import load_dotenv

from shared.config import QueueBackendType, get_settings
from shared.db import dispose_async_engine, get_async_session
from shared.enums import PipelineStep, TaskStatus
from shared.logging_config import configure_logging
from shared.queue import create_queue_publisher
from shared.queue.base import QueueMessage, QueuePublisher, QueueSubscriber
from shared.repositories import task
from shared.worker import serve
from worker_chunk.__main__ import subscribe as subscribe_chunk
from worker_crawl.__main__ import main as run_crawl
from worker_download.__main__ import subscribe as subscribe_download
from worker_embed.__main__ import subscribe as subscribe_embed
from worker_extract.__main__ import subscribe as subscribe_extract
from worker_metadata.__main__ import subscribe as subscribe_metadata
from worker_parse.__main__ import subscribe as subscribe_parse

logger = logging.getLogger("run_pipeline")

# Every step downstream of crawl, in pipeline order. Each registers its handler
# on the shared sync broker and returns the subscriber without starting it.
_SUBSCRIBING_WORKERS: tuple[Callable[[], QueueSubscriber], ...] = (
    subscribe_download,
    subscribe_parse,
    subscribe_metadata,
    subscribe_extract,
    subscribe_chunk,
    subscribe_embed,
)

# Crawl is not resumable this way: its "task" is discovering documents, and a
# pending crawl task is not a message any worker consumes.
_RESUMABLE_STEPS: tuple[PipelineStep, ...] = (
    PipelineStep.DOWNLOAD,
    PipelineStep.PARSE,
    PipelineStep.METADATA,
    PipelineStep.EXTRACT,
    PipelineStep.CHUNK,
    PipelineStep.EMBED,
)


async def _queue_pending_tasks(publisher: QueuePublisher) -> int:
    """Queue a message for every task still `pending`, oldest step first.

    Crawl only publishes for documents it has just discovered, so a document
    whose earlier run died mid-pipeline is invisible to it — it is already in
    `documents`, so the next crawl skips it, and its pending task is a message
    nobody will ever send. This is what re-drives those: `run_pipeline_step`
    skips a task that is already completed, so queueing a document that needs
    nothing costs one no-op.
    """
    queued = 0
    async with get_async_session() as session:
        for step in _RESUMABLE_STEPS:
            pending = await task.list_by_step_and_status(
                session, step, TaskStatus.PENDING
            )
            for pending_task in pending:
                publisher.publish(
                    step,
                    QueueMessage(
                        task_id=pending_task.id, document_id=pending_task.document_id
                    ),
                )
            queued += len(pending)

    # Downstream steps each open their own loop; this one must not leave a
    # connection pooled behind it. See `shared.db.dispose_async_engine`.
    await dispose_async_engine()
    return queued


async def _log_task_summary() -> None:
    """Report where every task in the corpus ended up, step by step.

    The per-document lines scroll past; this is the part worth reading after a
    long run. A step whose `completed` count is short of the one above it is
    where documents were lost, and a non-zero `failed` names the step to go
    looking at — the task rows carry the error messages.
    """
    async with get_async_session() as session:
        counts = await task.count_by_step_and_status(session)
    await dispose_async_engine()

    logger.info("Task status by step:")
    for step in PipelineStep:
        per_status = {status: counts.get((step, status), 0) for status in TaskStatus}
        if not any(per_status.values()):
            continue
        logger.info(
            "  %-9s %s",
            step,
            "  ".join(f"{status}={count}" for status, count in per_status.items()),
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_pipeline",
        description="Run crawl through embed in a single process (sync queue).",
    )
    parser.add_argument(
        "--years",
        default=None,
        help=(
            "Which decision years to crawl: 'current' (default), 'all', '2019', "
            "'2019-2021', or a comma-separated mix. Overrides CRAWL_YEARS."
        ),
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Also queue every task still pending from an earlier run, not just "
            "the documents this crawl discovers (default: enabled). "
            "--no-resume crawls only."
        ),
    )
    return parser.parse_args(argv)


def _require_sync_queue() -> None:
    """Refuse to run on any backend where composing workers is meaningless."""
    match get_settings().queue.queue_backend:
        case QueueBackendType.SYNC:
            return
        case backend:
            raise SystemExit(
                f"run_pipeline.py requires QUEUE_BACKEND=sync, found '{backend}'. "
                "On any other backend a subscriber blocks in start(), so the "
                "crawl step would never be reached — run each worker as its own "
                "process instead."
            )


def main() -> None:
    # Before anything logs: each worker's `main()` configures logging, but this
    # script calls their `subscribe()` instead, so nothing else would.
    configure_logging()
    load_dotenv()
    args = _parse_args()

    # Before subscribing: worker-embed verifies the embedding dimension at
    # startup, which is a real billed call. Fail on misconfiguration first.
    _require_sync_queue()

    # Every subscriber fronts the same process-wide broker, so serving any one
    # of them pumps the whole queue.
    pump, *_ = [subscribe() for subscribe in _SUBSCRIBING_WORKERS]

    logger.info("All downstream handlers registered; starting crawl")
    run_crawl(["--years", args.years] if args.years else [])

    if args.resume:
        publisher = create_queue_publisher(get_settings().queue)
        resumed = asyncio.run(_queue_pending_tasks(publisher))
        logger.info("Queued %d task(s) left pending by an earlier run", resumed)

    # Crawl queued one download message per new document and ran none of them.
    # Draining is the pipeline: download publishes parse, parse publishes
    # metadata, and so on until the queue empties and `serve` returns.
    logger.info("Crawl finished; draining the queue through embed")
    started_at = time.perf_counter()
    serve(pump, name="run_pipeline")

    logger.info("Pipeline run finished in %.1fs", time.perf_counter() - started_at)
    asyncio.run(_log_task_summary())


if __name__ == "__main__":
    main()
