import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EntityCreate(BaseModel):
    name: str
    type: str


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    created_at: datetime
