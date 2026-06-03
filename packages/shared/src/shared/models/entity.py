import uuid
from datetime import datetime

from sqlalchemy import VARCHAR, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.models.base import Base


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(VARCHAR, nullable=False)
    type: Mapped[str] = mapped_column(VARCHAR, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "type", name="uq_entities_name_type"),
        Index("ix_entities_name_type", "name", "type"),
        Index("ix_entities_type", "type"),
    )
