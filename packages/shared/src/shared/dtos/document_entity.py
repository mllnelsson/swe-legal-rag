import uuid

from pydantic import BaseModel, ConfigDict


class DocumentEntityCreate(BaseModel):
    document_id: uuid.UUID
    entity_id: uuid.UUID
    relevance: str


class DocumentEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    entity_id: uuid.UUID
    relevance: str
