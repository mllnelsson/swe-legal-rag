from typing import Any, Callable, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field


class QueueMessage(BaseModel):
    task_id: UUID
    document_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class QueuePublisher(Protocol):
    def publish(self, topic: str, message: QueueMessage) -> None: ...


@runtime_checkable
class QueueSubscriber(Protocol):
    def subscribe(self, topic: str, handler: Callable[[QueueMessage], None]) -> None: ...

    def start(self) -> None: ...

    def shutdown(self) -> None: ...
