"""Identifier lookups over a corpus where neither identifier is unique.

Integration rather than unit because what is under test is the query: the old
`scalar_one_or_none()` raised on the second row, and only a real result set shows
that.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate, DocumentUpdate


async def _seed(
    document_repo,
    session: AsyncSession,
    *,
    case_number: str | None = None,
    decision_number: str | None = None,
    decision_date: date | None = None,
) -> uuid.UUID:
    doc = await document_repo.create(
        session, DocumentCreate(source_url=f"https://example.com/{uuid.uuid4()}.pdf")
    )
    await document_repo.update(
        session,
        doc.id,
        DocumentUpdate(
            case_number=case_number,
            decision_number=decision_number,
            decision_date=decision_date,
        ),
    )
    await session.commit()
    return doc.id


async def test_shared_case_number_resolves_to_the_earliest_decision(
    document_repo, session: AsyncSession
) -> None:
    # Decisions 4/2020, 5/2020 and 8/2020 all carry ÖN 2020/12: jäv,
    # vilandeförklaring and muntlig förhandling in one ärende.
    first = await _seed(
        document_repo,
        session,
        case_number="2020-0012",
        decision_number="4/2020",
        decision_date=date(2020, 4, 23),
    )
    await _seed(
        document_repo,
        session,
        case_number="2020-0012",
        decision_number="8/2020",
        decision_date=date(2020, 5, 13),
    )

    found = await document_repo.get_by_case_number(session, "2020-0012")
    assert found is not None
    assert found.id == first


async def test_duplicated_decision_number_resolves_rather_than_raises(
    document_repo, session: AsyncSession
) -> None:
    # The source listing publishes 21/2021 twice, under two document ids, with
    # byte-identical text. A citation to it used to fail the citing document's
    # extract step.
    await _seed(
        document_repo,
        session,
        decision_number="21/2021",
        decision_date=date(2021, 8, 27),
    )
    await _seed(
        document_repo,
        session,
        decision_number="21/2021",
        decision_date=date(2021, 8, 27),
    )

    found = await document_repo.get_by_decision_number(session, "21/2021")
    assert found is not None
    assert found.decision_number == "21/2021"


async def test_an_identifier_no_document_carries_is_none(
    document_repo, session: AsyncSession
) -> None:
    assert await document_repo.get_by_case_number(session, "1999-0001") is None
    assert await document_repo.get_by_decision_number(session, "99/1999") is None
