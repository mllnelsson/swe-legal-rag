import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from shared.enums import TaskStatus

# NOTE: `step` / `status` are stored as plain ``str`` (matching the ``Mapped[str]``
# DB columns) but their *values* come from the ``PipelineStep`` / ``TaskStatus``
# enums, which business logic uses for every comparison and construction. The
# enums are str subclasses, so they flow into these fields without friction while
# keeping the finite vocabularies defined in one place (``shared.enums``).


class TaskCreate(BaseModel):
    document_id: uuid.UUID
    step: str
    status: str = TaskStatus.PENDING


class TaskStatusUpdate(BaseModel):
    status: str
    error_message: str | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    step: str
    status: str
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
