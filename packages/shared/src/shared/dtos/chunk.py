import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from shared.enums import ChunkSection


class ChunkCreate(BaseModel):
    document_id: uuid.UUID
    chunk_index: int
    chunk_text: str
    contextual_text: str | None = None
    embedding: list[float] | None = None
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    chunk_text: str
    contextual_text: str | None
    embedding: list[float] | None
    section: ChunkSection
    appendix_label: str | None
    created_at: datetime
