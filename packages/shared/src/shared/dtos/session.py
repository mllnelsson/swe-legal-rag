import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    history: list[Any] = []


class SessionUpdate(BaseModel):
    last_active_at: datetime | None = None
    history: list[Any] | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    last_active_at: datetime
    history: list[Any]
