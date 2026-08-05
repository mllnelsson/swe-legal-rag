"""Unit tests for the worker startup envelope.

These exist because the six worker `__main__` modules they replaced had no test
coverage at all: the duplicated startup block was the least-verified code in the
repo despite being on every ingestion path.

What is worth pinning here is the split itself — that `subscribe_step` registers
without blocking and without touching signal handlers, and that `serve` is the
only thing that does either. `scripts/run_pipeline.py` composes six workers into
one process and depends on exactly that.
"""

from __future__ import annotations

import signal
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import QueueBackendType, QueueSettings
from shared.enums import PipelineStep
from shared.queue.base import QueueMessage
from shared.queue.factory import create_queue_publisher
from shared.worker import serve, subscribe_step

_SYNC = QueueSettings(queue_backend=QueueBackendType.SYNC)


def _message() -> QueueMessage:
    return QueueMessage(task_id=uuid4(), document_id=uuid4())


@pytest.fixture
def no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """`subscribe_step` opens a session per message; these tests are not about
    the database, so hand the handler a placeholder instead of connecting."""

    @asynccontextmanager
    async def fake_session() -> AsyncIterator[None]:
        yield None

    monkeypatch.setattr("shared.worker.get_async_session", fake_session)


def test_subscribe_step_registers_without_starting(no_db: None) -> None:
    """The whole reason the module has two functions: a caller can register a
    handler and keep going."""
    received: list[QueueMessage] = []

    async def handle(message: QueueMessage, session: AsyncSession) -> None:
        received.append(message)

    subscriber = subscribe_step(
        topic=PipelineStep.DOWNLOAD, queue_settings=_SYNC, handle=handle
    )

    # Registered: publishing on the sync backend queues onto the shared broker,
    # and pumping it reaches this handler.
    message = _message()
    create_queue_publisher(_SYNC).publish(PipelineStep.DOWNLOAD, message)
    subscriber.start()

    assert received == [message]


def test_subscribe_step_leaves_signal_handlers_alone(no_db: None) -> None:
    """run_pipeline.py registers six workers in one process and must not
    inherit six sets of handlers; it used to reset them by hand afterwards."""
    before = (
        signal.getsignal(signal.SIGINT),
        signal.getsignal(signal.SIGTERM),
    )

    async def handle(message: QueueMessage, session: AsyncSession) -> None: ...

    subscribe_step(topic=PipelineStep.PARSE, queue_settings=_SYNC, handle=handle)

    assert (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)) == before


def test_scope_wraps_each_message(no_db: None) -> None:
    """The scope must be entered before the handler runs and exited after, so a
    ContextVar set in it is visible to everything the handler awaits."""
    events: list[str] = []

    @contextmanager
    def scope(message: QueueMessage) -> Iterator[None]:
        events.append("enter")
        yield
        events.append("exit")

    async def handle(message: QueueMessage, session: AsyncSession) -> None:
        events.append("handle")

    subscriber = subscribe_step(
        topic=PipelineStep.METADATA,
        queue_settings=_SYNC,
        handle=handle,
        scope=scope,
    )
    create_queue_publisher(_SYNC).publish(PipelineStep.METADATA, _message())
    subscriber.start()

    assert events == ["enter", "handle", "exit"]


def test_serve_installs_handlers_and_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[bool] = []
    shutdown: list[bool] = []

    class Subscriber:
        def subscribe(self, topic, handler) -> None: ...

        def start(self) -> None:
            started.append(True)

        def shutdown(self) -> None:
            shutdown.append(True)

    installed: dict[int, Callable[[int, object], None]] = {}
    monkeypatch.setattr(
        signal, "signal", lambda num, handler: installed.__setitem__(num, handler)
    )

    serve(Subscriber(), name="worker-test")

    assert started == [True]
    assert set(installed) == {signal.SIGINT, signal.SIGTERM}

    # The installed handler is what stops the subscriber.
    installed[signal.SIGTERM](signal.SIGTERM, None)
    assert shutdown == [True]
