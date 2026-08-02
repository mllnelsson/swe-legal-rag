"""The startup envelope every queue-consuming pipeline worker runs inside.

`shared.pipeline.run_pipeline_step` owns what happens *around one task*; this
owns what happens *around one process*. Together they leave a worker's
`__main__` with nothing but its own wiring: which settings, which repositories,
which providers, which `process_*`.

The split into :func:`subscribe_step` and :func:`serve` is the point of the
module. Registering a handler and blocking on a queue are separate concerns with
separate callers:

- a worker process does both, in that order;
- ``scripts/run_pipeline.py`` composes six workers into one process and wants
  only the first, because on the sync backend a publish is a direct call into
  whatever handler is registered *in this process*.

Fusing them — one ``run_worker()`` that registers and then blocks — is what
forced that script to call each worker's ``main()`` for its side effect and then
undo the signal handlers those calls had installed.

Tracing is injected rather than imported: `shared` must not depend on llm-core
(see `ai._observability`), and the trace context has to be entered *outside*
``asyncio.run`` so the loop inherits it — which rules out wrapping the handler.
`ai.worker_trace_scope` supplies the real one.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager, nullcontext

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import QueueSettings
from shared.db import get_async_session
from shared.enums import PipelineStep
from shared.queue import create_queue_subscriber
from shared.queue.base import QueueMessage, QueueSubscriber

__all__ = ["MessageScope", "StepHandler", "serve", "subscribe_step"]

logger = logging.getLogger(__name__)

# What a worker supplies: its unique work for one message, given a session.
# Everything around it — the session, the event loop, the scope — is this
# module's job.
type StepHandler = Callable[[QueueMessage, AsyncSession], Awaitable[None]]

# Whatever should be in effect for the duration of one message. Entered before
# the event loop exists, so a ContextVar set here is inherited by every task the
# handler spawns.
type MessageScope = Callable[[QueueMessage], AbstractContextManager[object]]


def subscribe_step(
    *,
    topic: PipelineStep,
    queue_settings: QueueSettings,
    handle: StepHandler,
    scope: MessageScope | None = None,
) -> QueueSubscriber:
    """Register `handle` for `topic` and return the subscriber, not yet started.

    Returning before starting is what lets one process host several workers.
    Call :func:`serve` to block on it.
    """
    subscriber = create_queue_subscriber(queue_settings)

    def handle_message(message: QueueMessage) -> None:
        async def run() -> None:
            async with get_async_session() as session:
                await handle(message, session)

        with nullcontext() if scope is None else scope(message):
            asyncio.run(run())

    subscriber.subscribe(topic, handle_message)
    logger.info("Registered handler for topic: %s", topic)
    return subscriber


def serve(subscriber: QueueSubscriber, *, name: str) -> None:
    """Block on `subscriber` until a shutdown signal arrives.

    The signal handlers are installed here rather than in :func:`subscribe_step`
    so a caller that only wants the registration never inherits them.
    """

    def shutdown_handler(_signum: int, _frame: object) -> None:
        logger.info("Shutdown signal received, stopping %s...", name)
        subscriber.shutdown()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info("%s starting", name)
    subscriber.start()
