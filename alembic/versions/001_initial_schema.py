"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-03

"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match `shared.config.DEFAULT_EMBEDDING_DIMENSION` — this migration bakes the
# value into DDL at upgrade time, while the Chunk model resolves it at import time.
# If the two disagree the mismatch only surfaces at embed time (EmbeddingDimensionError).
EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", 1024))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("gcs_uri", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("case_number", sa.String(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("decision_outcome", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("source_url", name="uq_documents_source_url"),
    )
    op.create_index("ix_documents_source_url", "documents", ["source_url"])

    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", "type", name="uq_entities_name_type"),
    )
    op.create_index("ix_entities_name_type", "entities", ["name", "type"])
    op.create_index("ix_entities_type", "entities", ["type"])

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_id", "step", name="uq_tasks_document_id_step"),
    )
    op.create_index("ix_tasks_document_id_step", "tasks", ["document_id", "step"])
    op.create_index("ix_tasks_step_status", "tasks", ["step", "status"])

    op.execute(f"""
        CREATE TABLE chunks (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents(id),
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            contextual_text TEXT,
            embedding vector({EMBEDDING_DIMENSION}) NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('swedish', chunk_text)) STORED,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_tsv_gin", "chunks", ["tsv"], postgresql_using="gin")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "document_entities",
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("relevance", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_document_entities_entity_id", "document_entities", ["entity_id"]
    )
    op.create_index(
        "ix_document_entities_document_id", "document_entities", ["document_id"]
    )

    op.create_table(
        "document_references",
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "target_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("reference_context", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_document_references_target_document_id",
        "document_references",
        ["target_document_id"],
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("history", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("document_references")
    op.drop_table("document_entities")
    op.drop_table("chunks")
    op.drop_table("tasks")
    op.drop_table("entities")
    op.drop_table("documents")
    op.execute("DROP EXTENSION IF EXISTS vector")
