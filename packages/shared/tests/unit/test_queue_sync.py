"""Unit tests for the in-process queue backend.

What matters here is that publishing *queues* rather than calling the handler.
The pipeline depends on it: every publish happens inside an event loop the
publishing step owns, and every handler wants a loop of its own, so a handler
that ran on the publisher's stack could not start one.
"""

from typing import Any
from uuid import uuid4

import pytest

from shared.errors import QueueHandlerError
from shared.queue.base import QueueMessage
from shared.queue.sync import SyncQueueBroker, SyncQueuePublisher, SyncQueueSubscriber


def _make_message(**kwargs: Any) -> QueueMessage:
    return QueueMessage(task_id=uuid4(), document_id=uuid4(), **kwargs)


def test_publish_queues_without_running_the_handler() -> None:
    broker = SyncQueueBroker()
    pub = SyncQueuePublisher(broker)
    sub = SyncQueueSubscriber(broker)
    received: list[QueueMessage] = []

    sub.subscribe("topic-a", lambda m: received.append(m))
    msg = _make_message()
    pub.publish("topic-a", msg)

    assert received == []

    sub.start()

    assert len(received) == 1
    assert received[0].task_id == msg.task_id


def test_publish_to_unregistered_topic_raises() -> None:
    """At publish time, not drain time: the traceback has to name the caller."""
    broker = SyncQueueBroker()
    pub = SyncQueuePublisher(broker)

    with pytest.raises(QueueHandlerError, match="No handler registered"):
        pub.publish("missing-topic", _make_message())


def test_multiple_topics_are_independent() -> None:
    broker = SyncQueueBroker()
    pub = SyncQueuePublisher(broker)
    sub = SyncQueueSubscriber(broker)

    received_a: list[QueueMessage] = []
    received_b: list[QueueMessage] = []

    sub.subscribe("topic-a", lambda m: received_a.append(m))
    sub.subscribe("topic-b", lambda m: received_b.append(m))

    msg_a = _make_message()
    msg_b = _make_message()
    pub.publish("topic-a", msg_a)
    pub.publish("topic-b", msg_b)
    sub.start()

    assert len(received_a) == 1
    assert received_a[0].task_id == msg_a.task_id
    assert len(received_b) == 1
    assert received_b[0].task_id == msg_b.task_id


def test_drain_runs_messages_handlers_publish() -> None:
    """The cascade the pipeline is made of: draining consumes a growing queue."""
    broker = SyncQueueBroker()
    pub = SyncQueuePublisher(broker)
    sub = SyncQueueSubscriber(broker)
    order: list[str] = []

    def download(message: QueueMessage) -> None:
        order.append("download")
        pub.publish("parse", message)

    def parse(_message: QueueMessage) -> None:
        order.append("parse")

    sub.subscribe("download", download)
    sub.subscribe("parse", parse)

    pub.publish("download", _make_message())
    sub.start()

    assert order == ["download", "parse"]


def test_drain_continues_after_a_failing_handler() -> None:
    """One document's failure must not abandon the rest of the run."""
    broker = SyncQueueBroker()
    pub = SyncQueuePublisher(broker)
    sub = SyncQueueSubscriber(broker)
    handled: list[QueueMessage] = []

    def flaky(message: QueueMessage) -> None:
        if not handled:
            handled.append(message)
            raise RuntimeError("boom")
        handled.append(message)

    sub.subscribe("topic-a", flaky)
    pub.publish("topic-a", _make_message())
    pub.publish("topic-a", _make_message())
    sub.start()

    assert len(handled) == 2


def test_shutdown_stops_the_drain() -> None:
    """SIGTERM mid-backfill leaves the queue unfinished rather than killing a step."""
    broker = SyncQueueBroker()
    pub = SyncQueuePublisher(broker)
    sub = SyncQueueSubscriber(broker)
    handled: list[QueueMessage] = []

    def stop_after_first(message: QueueMessage) -> None:
        handled.append(message)
        sub.shutdown()

    sub.subscribe("topic-a", stop_after_first)
    pub.publish("topic-a", _make_message())
    pub.publish("topic-a", _make_message())
    sub.start()

    assert len(handled) == 1
