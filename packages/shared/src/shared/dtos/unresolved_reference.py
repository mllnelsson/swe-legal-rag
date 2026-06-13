import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UnresolvedReferenceCreate(BaseModel):
    source_document_id: uuid.UUID
    target_case_number: str
    reference_context: str | None = None


class UnresolvedReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_document_id: uuid.UUID
    target_case_number: str
    reference_context: str | None
    created_at: datetime
