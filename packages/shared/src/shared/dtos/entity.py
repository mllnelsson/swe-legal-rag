import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

# `type` is stored as ``str`` (matching the ``Mapped[str]`` column); its values come
# from ``shared.enums.EntityType``, which the extraction logic uses. See the note in
# ``shared/dtos/task.py`` for the rationale.


class EntityCreate(BaseModel):
    name: str
    type: str


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    created_at: datetime
