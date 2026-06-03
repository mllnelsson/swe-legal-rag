import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    document_id: uuid.UUID
    step: str
    status: str = "pending"


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
