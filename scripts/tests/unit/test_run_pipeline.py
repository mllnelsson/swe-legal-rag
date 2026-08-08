"""The one thing `run_pipeline.main` gets to decide: what happens in which order.

Everything else it does is delegation, so these tests replace each collaborator
with a recorder and assert the sequence. The bug this guards against is the
resume pass running *after* crawl, where "pending" no longer distinguishes a
task stranded by an earlier run from one crawl created a second ago and has
already published — which published every newly crawled document twice.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest

import run_pipeline
from shared.config import QueueBackendType
from shared.enums import PipelineStep
from shared.queue.base import QueueMessage

RESUME = "resume"
CRAWL = "crawl"
SERVE = "serve"

# `main` builds one subscriber per downstream worker and serves the first.
SUBSCRIBING_WORKER_COUNT = 6


class _RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, QueueMessage]] = []

    def publish(self, topic: str, message: QueueMessage) -> None:
        self.published.append((topic, message))


def _pending_task() -> Any:
    return type("_Task", (), {"id": uuid4(), "document_id": uuid4()})()


@asynccontextmanager
async def _null_session() -> AsyncIterator[object]:
    yield object()


async def _noop() -> None:
    return None


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record the order of the three steps `main` sequences, and run none of them."""
    recorded: list[str] = []

    async def fake_queue_pending(_publisher: object) -> int:
        recorded.append(RESUME)
        return 0

    def fake_crawl(_argv: list[str]) -> None:
        recorded.append(CRAWL)

    def fake_serve(_subscriber: object, **_kwargs: object) -> None:
        recorded.append(SERVE)

    monkeypatch.setattr(run_pipeline, "_queue_pending_tasks", fake_queue_pending)
    monkeypatch.setattr(run_pipeline, "run_crawl", fake_crawl)
    monkeypatch.setattr(run_pipeline, "serve", fake_serve)
    monkeypatch.setattr(run_pipeline, "_log_task_summary", _noop)
    monkeypatch.setattr(run_pipeline, "_require_sync_queue", lambda: None)
    monkeypatch.setattr(run_pipeline, "create_queue_publisher", lambda _s: object())
    monkeypatch.setattr(run_pipeline, "load_dotenv", lambda: None)
    monkeypatch.setattr(run_pipeline, "configure_logging", lambda: None)
    monkeypatch.setattr(
        run_pipeline,
        "_SUBSCRIBING_WORKERS",
        tuple(lambda: object() for _ in range(SUBSCRIBING_WORKER_COUNT)),
    )
    yield recorded


def test_pending_tasks_are_resumed_before_crawl(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["run_pipeline"])

    run_pipeline.main()

    assert calls == [RESUME, CRAWL, SERVE]


def test_no_resume_crawls_only(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["run_pipeline", "--no-resume"])

    run_pipeline.main()

    assert calls == [CRAWL, SERVE]


def test_a_non_sync_backend_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A subscriber blocks in `start()` on every other backend, so crawl never runs."""

    class _Settings:
        queue = type("_Q", (), {"queue_backend": QueueBackendType.PUBSUB})()

    monkeypatch.setattr(run_pipeline, "get_settings", lambda: _Settings())

    with pytest.raises(SystemExit, match="requires QUEUE_BACKEND=sync"):
        run_pipeline._require_sync_queue()


async def test_each_pending_task_is_published_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every resumable step is drained, and each pending task yields one message."""
    pending = {
        PipelineStep.DOWNLOAD: [_pending_task(), _pending_task()],
        PipelineStep.EMBED: [_pending_task()],
    }

    async def fake_list(
        _session: object, step: PipelineStep, _status: Any
    ) -> list[Any]:
        return pending.get(step, [])

    monkeypatch.setattr(run_pipeline.task, "list_by_step_and_status", fake_list)
    monkeypatch.setattr(run_pipeline, "get_async_session", _null_session)
    monkeypatch.setattr(run_pipeline, "dispose_async_engine", _noop)
    publisher = _RecordingPublisher()

    queued = await run_pipeline._queue_pending_tasks(publisher)

    assert queued == 3
    assert [topic for topic, _ in publisher.published] == [
        PipelineStep.DOWNLOAD,
        PipelineStep.DOWNLOAD,
        PipelineStep.EMBED,
    ]
    assert {message.task_id for _, message in publisher.published} == {
        task.id for tasks in pending.values() for task in tasks
    }
