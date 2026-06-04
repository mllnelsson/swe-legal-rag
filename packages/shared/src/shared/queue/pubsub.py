from typing import Any, Callable

try:
    from google.cloud import pubsub_v1
except ImportError:
    pubsub_v1 = None  # type: ignore[assignment]

from shared.queue.base import QueueMessage

_INSTALL_MSG = (
    "google-cloud-pubsub is not installed. "
    "Install it with: uv add 'shared[pubsub]' or uv add google-cloud-pubsub"
)


class PubSubQueuePublisher:
    def __init__(self, project_id: str) -> None:
        if pubsub_v1 is None:
            raise ImportError(_INSTALL_MSG)
        self._project_id = project_id
        self._client = pubsub_v1.PublisherClient()

    def publish(self, topic: str, message: QueueMessage) -> None:
        topic_path = f"projects/{self._project_id}/topics/{topic}"
        data = message.model_dump_json().encode("utf-8")
        self._client.publish(topic_path, data)


class PubSubQueueSubscriber:
    def __init__(self, project_id: str) -> None:
        if pubsub_v1 is None:
            raise ImportError(_INSTALL_MSG)
        self._project_id = project_id
        self._handlers: dict[str, Callable[[QueueMessage], None]] = {}
        self._futures: list[Any] = []

    def subscribe(self, topic: str, handler: Callable[[QueueMessage], None]) -> None:
        self._handlers[topic] = handler

    def start(self) -> None:
        client = pubsub_v1.SubscriberClient()
        for topic, handler in self._handlers.items():
            subscription_path = f"projects/{self._project_id}/subscriptions/{topic}"

            def _callback(
                message: Any,
                _handler: Callable[[QueueMessage], None] = handler,
            ) -> None:
                try:
                    queue_message = QueueMessage.model_validate_json(message.data)
                    _handler(queue_message)
                    message.ack()
                except Exception:
                    message.nack()

            future = client.subscribe(subscription_path, callback=_callback)
            self._futures.append(future)

        for future in self._futures:
            future.result()

    def shutdown(self) -> None:
        for future in self._futures:
            future.cancel()
        self._futures.clear()
