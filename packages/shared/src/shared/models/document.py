import uuid
from datetime import date, datetime

from sqlalchemy import (
    DATE,
    INTEGER,
    TEXT,
    VARCHAR,
    DateTime,
    Index,
    UniqueConstraint,
)
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
    # Identity and metadata carried over from the Svenska kyrkan OData listing. Nullable
    # because rows predating the OData crawler (HTML scraping) have no listing behind them.
    source_document_id: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    source_headline: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    # The beslutsnummer the headline states, canonical "N/YYYY". The crawl dedup
    # key: source_url and source_document_id both identify the *listing entry*,
    # and the listing published 21/2021 twice under two ids. Nullable because a
    # headline the parser does not recognise must still be crawlable.
    source_decision_number: Mapped[str | None] = mapped_column(VARCHAR, nullable=True)
    source_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    gcs_uri: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    summary: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    # Ärendenummer, canonical "YYYY-NNNN" (see shared.segmentation).
    case_number: Mapped[str | None] = mapped_column(VARCHAR, nullable=True)
    # Beslutsnummer, canonical "N/YYYY" — a separate identifier space from
    # case_number. Decisions cite each other by either, so both must be resolvable.
    decision_number: Mapped[str | None] = mapped_column(VARCHAR, nullable=True)
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
        UniqueConstraint("source_document_id", name="uq_documents_source_document_id"),
        UniqueConstraint(
            "source_decision_number", name="uq_documents_source_decision_number"
        ),
        Index("ix_documents_source_url", "source_url"),
        Index("ix_documents_decision_number", "decision_number"),
    )
