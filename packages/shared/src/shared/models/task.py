import uuid
from datetime import datetime

from sqlalchemy import TEXT, VARCHAR, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    step: Mapped[str] = mapped_column(VARCHAR, nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR, nullable=False)
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("document_id", "step", name="uq_tasks_document_id_step"),
        Index("ix_tasks_document_id_step", "document_id", "step"),
        Index("ix_tasks_step_status", "step", "status"),
    )
