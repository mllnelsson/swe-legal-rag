"""add sessions.context — the per-conversation carry-over blob

Revision ID: 007
Revises: 006
Create Date: 2026-08-28

A conversation's turns are stored in `sessions.history`; this adds a second
JSONB column, `context`, holding the running carry-over the chat agent injects
into its planning step at the start of every turn. The two are different in kind:
`history` is the transcript the user sees, `context` is the agent's working notes
about the conversation so far, and only the transcript is ever shown.

Additive and safe on the live table: `NOT NULL DEFAULT '{}'::jsonb` backfills
every existing row with an empty blob — the same thing a brand-new conversation
starts from — so nothing has to be recomputed and no history is touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "context",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "context")
