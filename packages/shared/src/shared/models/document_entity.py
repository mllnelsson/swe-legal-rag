import uuid

from sqlalchemy import VARCHAR, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base


class DocumentEntity(Base):
    __tablename__ = "document_entities"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True, nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True, nullable=False
    )
    relevance: Mapped[str] = mapped_column(VARCHAR, nullable=False)

    __table_args__ = (
        Index("ix_document_entities_entity_id", "entity_id"),
        Index("ix_document_entities_document_id", "document_id"),
    )
