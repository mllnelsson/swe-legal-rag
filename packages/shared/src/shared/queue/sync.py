from typing import Callable

from shared.queue.base import QueueMessage


class SyncQueueBroker:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[QueueMessage], None]] = {}

    def register(self, topic: str, handler: Callable[[QueueMessage], None]) -> None:
        self._handlers[topic] = handler

    def dispatch(self, topic: str, message: QueueMessage) -> None:
        handler = self._handlers.get(topic)
        if handler is None:
            raise ValueError(f"No handler registered for topic: {topic!r}")
        handler(message)


class SyncQueuePublisher:
    def __init__(self, broker: SyncQueueBroker) -> None:
        self._broker = broker

    def publish(self, topic: str, message: QueueMessage) -> None:
        self._broker.dispatch(topic, message)


class SyncQueueSubscriber:
    def __init__(self, broker: SyncQueueBroker) -> None:
        self._broker = broker

    def subscribe(self, topic: str, handler: Callable[[QueueMessage], None]) -> None:
        self._broker.register(topic, handler)

    def start(self) -> None:
        pass

    def shutdown(self) -> None:
        pass
