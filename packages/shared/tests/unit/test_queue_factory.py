import importlib
from uuid import uuid4

import pytest

from shared.config import QueueBackendType, QueueSettings
from shared.queue.base import QueueMessage
from shared.queue.factory import create_queue_publisher, create_queue_subscriber
from shared.queue.sync import SyncQueuePublisher, SyncQueueSubscriber


def _sync_settings() -> QueueSettings:
    return QueueSettings(queue_backend=QueueBackendType.SYNC)


def test_factory_returns_sync_publisher_for_sync_backend() -> None:
    pub = create_queue_publisher(_sync_settings())
    assert isinstance(pub, SyncQueuePublisher)


def test_factory_returns_sync_subscriber_for_sync_backend() -> None:
    sub = create_queue_subscriber(_sync_settings())
    assert isinstance(sub, SyncQueueSubscriber)


def test_factory_shared_broker_allows_pub_sub_communication() -> None:
    import shared.queue.factory as factory_module

    factory_module._sync_broker = None

    settings = _sync_settings()
    pub = create_queue_publisher(settings)
    sub = create_queue_subscriber(settings)

    received: list[QueueMessage] = []
    sub.subscribe("pipeline", lambda m: received.append(m))

    msg = QueueMessage(task_id=uuid4(), document_id=uuid4())
    pub.publish("pipeline", msg)

    assert len(received) == 1
    assert received[0].task_id == msg.task_id


def test_factory_raises_for_unknown_backend() -> None:
    settings = QueueSettings.__new__(QueueSettings)
    object.__setattr__(settings, "queue_backend", "unknown")  # type: ignore[arg-type]
    object.__setattr__(settings, "pubsub_project_id", None)

    with pytest.raises(ValueError, match="Unknown queue backend"):
        create_queue_publisher(settings)
