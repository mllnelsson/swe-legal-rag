import uuid
from datetime import datetime

from sqlalchemy import TEXT, VARCHAR, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.models.base import Base


class UnresolvedReference(Base):
    __tablename__ = "unresolved_references"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    target_case_number: Mapped[str] = mapped_column(VARCHAR, nullable=False)
    reference_context: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "target_case_number",
            name="uq_unresolved_refs_source_case",
        ),
        Index("ix_unresolved_references_target_case_number", "target_case_number"),
        Index("ix_unresolved_references_source_document_id", "source_document_id"),
    )
