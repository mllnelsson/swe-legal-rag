"""add source listing metadata to documents

Revision ID: 003
Revises: 002
Create Date: 2026-07-19

The crawl worker now reads the Svenska kyrkan OData listing instead of scraping HTML,
which hands it the CMS document id, headline and publish date for free. Persisting them
gives a stable numeric identity for a decision (independent of URL spelling) and lets the
parse step cross-check the case number it extracts from the PDF text.

All three columns are nullable so rows created by the previous HTML scraper survive the
upgrade. Postgres permits repeated NULLs under a UNIQUE constraint, so those legacy rows
do not collide on source_document_id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents", sa.Column("source_document_id", sa.Integer(), nullable=True)
    )
    op.add_column("documents", sa.Column("source_headline", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_documents_source_document_id", "documents", ["source_document_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_source_document_id", "documents", type_="unique")
    op.drop_column("documents", "source_published_at")
    op.drop_column("documents", "source_headline")
    op.drop_column("documents", "source_document_id")
