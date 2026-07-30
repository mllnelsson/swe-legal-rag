"""make chunks.embedding nullable

Revision ID: 005
Revises: 004
Create Date: 2026-07-29

Ingestion writes a chunk row before it has a vector. The chunk worker cuts the text and
inserts the rows; the embed worker runs afterwards as a separate pipeline step and fills
the column in via chunk_repo.update_embeddings() — a bulk UPDATE, not an INSERT. Between
those two steps a chunk legitimately has no embedding, so the NOT NULL that migration 001
put on the column made the normal path impossible: worker-chunk could not insert at all.

The rest of the stack already assumed nullable. ChunkCreate.embedding defaults to None,
ChunkRead types it `list[float] | None`, and the vector search query filters
`WHERE embedding IS NOT NULL` — a predicate with nothing to do if the column can never be
null. This migration makes the schema agree with them rather than the other way round.

The HNSW index is unaffected: Postgres simply does not index NULL rows, which is exactly
what that IS NOT NULL filter already relies on. Chunks awaiting embedding are invisible to
vector search and become visible when the embed step writes their vector.

The downgrade restores NOT NULL, so it fails if any chunk is still awaiting a vector.
That is the honest behaviour — there is no correct value to backfill, and inventing a zero
vector would put a chunk at a meaningless distance from every query.
"""

import os
from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same value, same reason as migration 001: the column type has to be restated for
# ALTER COLUMN, and it must match `shared.config.DEFAULT_EMBEDDING_DIMENSION`.
EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", 1024))


def upgrade() -> None:
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(EMBEDDING_DIMENSION),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(EMBEDDING_DIMENSION),
        nullable=False,
    )
