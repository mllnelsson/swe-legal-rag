import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import TEXT, VARCHAR, INTEGER, Computed, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.config import EMBEDDING_DIMENSION
from shared.enums import ChunkSection
from shared.models.base import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(INTEGER, nullable=False)
    chunk_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    contextual_text: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    # Which part of the source PDF this came from. Retrieval filters on it so the
    # appealed decision is never cited as the nämnd's own reasoning.
    section: Mapped[str] = mapped_column(
        VARCHAR, nullable=False, server_default=ChunkSection.BODY.value
    )
    # The "Bilaga A" label, when section is APPENDIX.
    appendix_label: Mapped[str | None] = mapped_column(VARCHAR, nullable=True)
    # Null until the embed worker runs. Chunking and embedding are separate pipeline
    # steps, so a chunk exists before its vector does — see /pipeline/embed.md.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('swedish', chunk_text)", persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_section", "section"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv_gin", "tsv", postgresql_using="gin"),
    )
