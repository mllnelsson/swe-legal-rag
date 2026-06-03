import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    source_url: str


class DocumentUpdate(BaseModel):
    gcs_uri: str | None = None
    raw_text: str | None = None
    summary: str | None = None
    case_number: str | None = None
    decision_date: date | None = None
    decision_outcome: str | None = None
    category: str | None = None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_url: str
    gcs_uri: str | None
    raw_text: str | None
    summary: str | None
    case_number: str | None
    decision_date: date | None
    decision_outcome: str | None
    category: str | None
    created_at: datetime
    updated_at: datetime
