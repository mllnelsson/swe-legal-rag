import uuid

from sqlalchemy import TEXT, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base


class DocumentReference(Base):
    __tablename__ = "document_references"

    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True, nullable=False
    )
    target_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True, nullable=False
    )
    reference_context: Mapped[str | None] = mapped_column(TEXT, nullable=True)

    __table_args__ = (
        Index("ix_document_references_target_document_id", "target_document_id"),
    )
