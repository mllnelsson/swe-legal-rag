import uuid

from pydantic import BaseModel, ConfigDict


class DocumentReferenceCreate(BaseModel):
    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    reference_context: str | None = None


class DocumentReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    reference_context: str | None
