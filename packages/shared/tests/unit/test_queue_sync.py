import json
from typing import Any
from uuid import uuid4

import pytest

from shared.errors import QueueHandlerError
from shared.queue.base import QueueMessage
from shared.queue.sync import SyncQueueBroker, SyncQueuePublisher, SyncQueueSubscriber


def _make_message(**kwargs: Any) -> QueueMessage:
    return QueueMessage(task_id=uuid4(), document_id=uuid4(), **kwargs)


def test_publish_triggers_registered_handler() -> None:
    broker = SyncQueueBroker()
    pub = SyncQueuePublisher(broker)
    sub = SyncQueueSubscriber(broker)
    received: list[QueueMessage] = []

    sub.subscribe("topic-a", lambda m: received.append(m))
    msg = _make_message()
    pub.publish("topic-a", msg)

    assert len(received) == 1
    assert received[0].task_id == msg.task_id


def test_publish_to_unregistered_topic_raises() -> None:
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

    assert len(received_a) == 1
    assert received_a[0].task_id == msg_a.task_id
    assert len(received_b) == 1
    assert received_b[0].task_id == msg_b.task_id


def test_queue_message_serialization_roundtrip() -> None:
    original = QueueMessage(
        task_id=uuid4(),
        document_id=uuid4(),
        payload={"key": "val", "number": 42},
    )
    json_str = original.model_dump_json()
    restored = QueueMessage.model_validate_json(json_str)

    assert restored.task_id == original.task_id
    assert restored.document_id == original.document_id
    assert restored.payload == original.payload


def test_queue_message_default_payload_is_empty_dict() -> None:
    msg = QueueMessage(task_id=uuid4(), document_id=uuid4())
    parsed = json.loads(msg.model_dump_json())
    assert parsed["payload"] == {}


def test_start_and_shutdown_are_noops() -> None:
    broker = SyncQueueBroker()
    sub = SyncQueueSubscriber(broker)
    sub.start()
    sub.shutdown()
