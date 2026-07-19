"""add unresolved_references table

Revision ID: 002
Revises: 001
Create Date: 2026-06-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "unresolved_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column("target_case_number", sa.String(), nullable=False),
        sa.Column("reference_context", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source_document_id",
            "target_case_number",
            name="uq_unresolved_refs_source_case",
        ),
    )
    op.create_index(
        "ix_unresolved_references_target_case_number",
        "unresolved_references",
        ["target_case_number"],
    )
    op.create_index(
        "ix_unresolved_references_source_document_id",
        "unresolved_references",
        ["source_document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_unresolved_references_source_document_id")
    op.drop_index("ix_unresolved_references_target_case_number")
    op.drop_table("unresolved_references")
