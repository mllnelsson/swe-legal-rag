"""add documents.source_decision_number as the crawl dedup key

Revision ID: 006
Revises: 005
Create Date: 2026-08-08

The crawler de-duplicates on `source_url`, which is a pure function of the CMS
document id. That is the listing's identity for a decision, not the decision's:
the listing published 21/2021 twice, under ids 2265536 and 2266136, three days
apart, and the corpus held it twice with byte-identical text, its own chunks and
its own entity links.

The listing headline states the decision's real identity — "Beslut 2021-21
Beslutsprövning" — so this column holds the beslutsnummer parsed out of it, in
the same canonical "N/YYYY" form as `decision_number`. Over the 2020-2026 corpus
all 185 headlines parse, all 185 agree with the beslutsnummer later read out of
the PDF, and 21/2021 is the only collision.

Nullable, because a headline the parser does not recognise must still be
crawlable; unique, because when it *is* recognised it names the decision. The
crawl worker checks it before creating a row, so the constraint is a backstop
rather than the mechanism.

The backfill repeats the shape of `shared.source_headline._SOURCE_HEADLINE_RE`,
which is the authority for it — migrations here import no application code, so
the two are deliberately kept in step by hand. It will fail on a database that
still holds a duplicate; that is the point, and the duplicate has to be resolved
first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# "Beslut 2026-23  Avskrivning" -> groups ("2026", "23"). The listing sometimes
# doubles the space, and writes the sequence without zero padding.
_HEADLINE_PATTERN = r"^[ \t]*Beslut[ \t]+([0-9]{4})-([0-9]{1,3})[ \t]+"


def upgrade() -> None:
    op.add_column(
        "documents", sa.Column("source_decision_number", sa.VARCHAR(), nullable=True)
    )
    op.execute(
        sa.text(
            """
            UPDATE documents
            SET source_decision_number =
                (regexp_match(source_headline, :pattern))[2]::int
                || '/'
                || (regexp_match(source_headline, :pattern))[1]
            WHERE source_headline ~ :pattern
            """
        ).bindparams(pattern=_HEADLINE_PATTERN)
    )
    op.create_unique_constraint(
        "uq_documents_source_decision_number", "documents", ["source_decision_number"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_documents_source_decision_number", "documents", type_="unique"
    )
    op.drop_column("documents", "source_decision_number")
