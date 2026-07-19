import uuid
from datetime import date, datetime

from sqlalchemy import DATE, TEXT, VARCHAR, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.models.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_url: Mapped[str] = mapped_column(TEXT, nullable=False)
    gcs_uri: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    summary: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    case_number: Mapped[str | None] = mapped_column(VARCHAR, nullable=True)
    decision_date: Mapped[date | None] = mapped_column(DATE, nullable=True)
    decision_outcome: Mapped[str | None] = mapped_column(VARCHAR, nullable=True)
    category: Mapped[str | None] = mapped_column(VARCHAR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("source_url", name="uq_documents_source_url"),
        Index("ix_documents_source_url", "source_url"),
    )
