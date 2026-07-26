"""add chunk section provenance and document decision number

Revision ID: 004
Revises: 003
Create Date: 2026-07-26

Överklagandenämnden publishes one PDF per ärende, and that PDF physically contains the
decision that was appealed, pasted in under a "Bilaga X" label. Flattened into
documents.raw_text the two were indistinguishable, so the lower instance's reasoning —
often the very reasoning the nämnd overturned — could be retrieved, summarised and cited
as the nämnd's own. chunks.section records which part a chunk came from so retrieval can
default to the body and citations can say which they are quoting.

section is NOT NULL with a 'body' server default: every pre-existing chunk was cut from
an unsegmented raw_text, and treating it as body preserves today's retrieval behaviour
until the document is re-chunked. Re-chunking is DELETE+INSERT (see chunk_repo), so a
re-run replaces those rows with correctly-sectioned ones.

documents.decision_number holds the beslutsnummer ("1/2026") from the decision trailer.
It is a different identifier space from case_number ("2025-0017") — a decision carries
both, and cross-references in the corpus use either form, so both must be resolvable or
a "beslut 13/2025" reference sits in unresolved_references forever.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "section", sa.VARCHAR(), nullable=False, server_default=sa.text("'body'")
        ),
    )
    op.add_column("chunks", sa.Column("appendix_label", sa.VARCHAR(), nullable=True))
    op.create_index("ix_chunks_section", "chunks", ["section"])

    op.add_column(
        "documents", sa.Column("decision_number", sa.VARCHAR(), nullable=True)
    )
    op.create_index("ix_documents_decision_number", "documents", ["decision_number"])


def downgrade() -> None:
    op.drop_index("ix_documents_decision_number", table_name="documents")
    op.drop_column("documents", "decision_number")

    op.drop_index("ix_chunks_section", table_name="chunks")
    op.drop_column("chunks", "appendix_label")
    op.drop_column("chunks", "section")
