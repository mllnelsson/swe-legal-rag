import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChunkCreate(BaseModel):
    document_id: uuid.UUID
    chunk_index: int
    chunk_text: str
    contextual_text: str | None = None
    embedding: list[float] | None = None


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    chunk_text: str
    contextual_text: str | None
    embedding: list[float] | None
    created_at: datetime
