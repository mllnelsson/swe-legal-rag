"""The in-process queue backend: a real queue, not a call stack.

`publish` appends to a pending FIFO and returns. Handlers run later, from
:meth:`SyncQueueBroker.drain`. The obvious alternative — calling the topic's
handler directly from `publish` — is what this used to do, and it cannot work
for this pipeline:

- Every handler owns an event loop (`shared.worker` runs `asyncio.run` per
  message), and every publish happens *inside* one, because the publishing step
  is itself async. Dispatching inline therefore reentered a running loop:
  ``RuntimeError: asyncio.run() cannot be called from a running event loop``.
- Inline dispatch also ran the entire downstream pipeline inside the publishing
  step's ``try`` block, since `shared.pipeline.run_pipeline_step` publishes
  before marking its own task completed. A failure in embed rolled back and
  failed the download task that had already succeeded.

Queueing fixes both. The publishing step returns immediately, finishes its own
bookkeeping, and the next step runs afterwards from the pump — in its own loop,
with its own session, against its own task row.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Callable

from shared.errors import QueueHandlerError
from shared.queue.base import QueueMessage

logger = logging.getLogger(__name__)


class SyncQueueBroker:
    """The handler registry and pending queue shared by every worker in the process."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[QueueMessage], None]] = {}
        self._pending: deque[tuple[str, QueueMessage]] = deque()
        self._draining = False
        self._stopped = False

    def register(self, topic: str, handler: Callable[[QueueMessage], None]) -> None:
        self._handlers[topic] = handler

    def enqueue(self, topic: str, message: QueueMessage) -> None:
        """Queue `message` for `topic`, to be run by the next :meth:`drain`.

        The topic is resolved now rather than at drain time so that an
        unsubscribed topic fails the publishing step, where the traceback still
        names the caller. Running one worker on its own under
        ``QUEUE_BACKEND=sync`` is the common way to hit that, and queueing to
        nobody would turn a loud failure into a silent no-op.
        """
        if topic not in self._handlers:
            raise QueueHandlerError(f"No handler registered for topic: {topic!r}")
        self._pending.append((topic, message))

    def dispatch(self, topic: str, message: QueueMessage) -> None:
        """Run `topic`'s handler now, on the caller's stack.

        Safe only when the handler needs nothing the caller is already holding —
        an event loop in particular. :meth:`drain` uses it; `SyncQueuePublisher`
        deliberately does not.
        """
        handler = self._handlers.get(topic)
        if handler is None:
            raise QueueHandlerError(f"No handler registered for topic: {topic!r}")
        handler(message)

    def drain(self) -> None:
        """Run queued messages until the queue empties or a stop is requested.

        Call with no event loop running: each handler starts its own. Handlers
        publish as they go, so the queue grows while it is consumed — this loop
        *is* the pipeline, one step at a time.
        """
        if self._draining:
            return

        self._draining = True
        try:
            while self._pending and not self._stopped:
                topic, message = self._pending.popleft()
                try:
                    self.dispatch(topic, message)
                except Exception:
                    # One document must not end the run. Its task row already
                    # carries the failure — `shared.pipeline.run_pipeline_step`
                    # records it before re-raising — and redelivery is a real
                    # broker's job, so the message is dropped here.
                    logger.exception(
                        "Handler for topic %s failed for document %s",
                        topic,
                        message.document_id,
                    )
        finally:
            self._draining = False

    def request_stop(self) -> None:
        """Stop the drain once the message in flight finishes.

        One-way: this is the shutdown signal, and the process is on its way out.
        """
        self._stopped = True


class SyncQueuePublisher:
    def __init__(self, broker: SyncQueueBroker) -> None:
        self._broker = broker

    def publish(self, topic: str, message: QueueMessage) -> None:
        self._broker.enqueue(topic, message)


class SyncQueueSubscriber:
    def __init__(self, broker: SyncQueueBroker) -> None:
        self._broker = broker

    def subscribe(self, topic: str, handler: Callable[[QueueMessage], None]) -> None:
        self._broker.register(topic, handler)

    def start(self) -> None:
        """Pump the queue until it is empty, then return.

        The sync analogue of blocking on a subscription. Nothing outside this
        process can produce a message, so an empty queue means the run is over —
        there is nothing left to wait for.
        """
        self._broker.drain()

    def shutdown(self) -> None:
        self._broker.request_stop()
