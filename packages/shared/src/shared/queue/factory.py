from shared.config import QueueBackendType, QueueSettings
from shared.queue.base import QueuePublisher, QueueSubscriber

_sync_broker: object = None


def _get_sync_broker() -> "object":
    global _sync_broker
    if _sync_broker is None:
        from shared.queue.sync import SyncQueueBroker

        _sync_broker = SyncQueueBroker()
    return _sync_broker


def create_queue_publisher(settings: QueueSettings) -> QueuePublisher:
    match settings.queue_backend:
        case QueueBackendType.SYNC:
            from shared.queue.sync import SyncQueueBroker, SyncQueuePublisher

            broker = _get_sync_broker()
            assert isinstance(broker, SyncQueueBroker)
            return SyncQueuePublisher(broker)
        case QueueBackendType.PUBSUB:
            from shared.queue.pubsub import PubSubQueuePublisher

            return PubSubQueuePublisher(settings.pubsub_project_id)  # type: ignore[arg-type]
        case _:
            raise ValueError(f"Unknown queue backend: {settings.queue_backend}")


def create_queue_subscriber(settings: QueueSettings) -> QueueSubscriber:
    match settings.queue_backend:
        case QueueBackendType.SYNC:
            from shared.queue.sync import SyncQueueBroker, SyncQueueSubscriber

            broker = _get_sync_broker()
            assert isinstance(broker, SyncQueueBroker)
            return SyncQueueSubscriber(broker)
        case QueueBackendType.PUBSUB:
            from shared.queue.pubsub import PubSubQueueSubscriber

            return PubSubQueueSubscriber(settings.pubsub_project_id)  # type: ignore[arg-type]
        case _:
            raise ValueError(f"Unknown queue backend: {settings.queue_backend}")
