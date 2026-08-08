import uuid

from sqlalchemy import nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from shared.dtos.document import DocumentCreate, DocumentRead, DocumentUpdate
from shared.models.document import Document

DEFAULT_PAGE_SIZE = 100


async def create(session: AsyncSession, dto: DocumentCreate) -> DocumentRead:
    doc = Document(**dto.model_dump())
    session.add(doc)
    await session.flush()
    await session.refresh(doc)
    return DocumentRead.model_validate(doc)


async def get_by_id(
    session: AsyncSession, document_id: uuid.UUID
) -> DocumentRead | None:
    doc = await session.get(Document, document_id)
    return DocumentRead.model_validate(doc) if doc else None


async def get_by_source_url(
    session: AsyncSession, source_url: str
) -> DocumentRead | None:
    result = await session.execute(
        select(Document).where(Document.source_url == source_url)
    )
    doc = result.scalar_one_or_none()
    return DocumentRead.model_validate(doc) if doc else None


async def get_by_source_decision_number(
    session: AsyncSession, source_decision_number: str
) -> DocumentRead | None:
    """Look up by the beslutsnummer the *listing headline* states.

    The crawl dedup key. Unique, unlike `decision_number` — this one is read from
    the listing before anything is downloaded, and one beslutsnummer is one
    decision however many listing entries point at it.
    """
    result = await session.execute(
        select(Document).where(
            Document.source_decision_number == source_decision_number
        )
    )
    doc = result.scalar_one_or_none()
    return DocumentRead.model_validate(doc) if doc else None


async def get_by_case_number(
    session: AsyncSession, case_number: str
) -> DocumentRead | None:
    """Look up by ärendenummer ("2025-0017"), earliest decision first.

    Neither identifier is unique in the corpus, so neither lookup may assume it.
    An ärendenummer names an *ärende*, and the nämnd rules more than once within
    one: decisions 4/2020, 5/2020 and 8/2020 all carry ÖN 2020/12 — jäv,
    vilandeförklaring and muntlig förhandling in a single matter. A citation to the
    number names the matter, and nothing in the citing sentence says which ruling.

    Taking the earliest is deterministic, not correct — there is no correct answer
    to pick. What it replaces is worse than either: `scalar_one_or_none` raised on
    the second row, which failed the *citing* document's extract step over an
    ambiguity in the document it cited.
    """
    return await _first_matching(session, Document.case_number == case_number)


async def get_by_decision_number(
    session: AsyncSession, decision_number: str
) -> DocumentRead | None:
    """Look up by beslutsnummer ("1/2026") rather than ärendenummer.

    Decisions cite each other in both identifier spaces, so reference resolution
    has to try both.

    Not declared unique, and not for `get_by_case_number`'s reason: a
    beslutsnummer really does name one decision. The corpus once held 21/2021
    twice because the listing published it under two document ids and crawl
    de-duplicated on the id — a defect now prevented at the source by
    `get_by_source_decision_number`. The tolerance stays because this column is
    filled by the metadata step from the PDF's own text, which can misread, and
    failing a *citing* document's extract over that is worse than answering with
    the earliest match. See `get_by_case_number`.
    """
    return await _first_matching(session, Document.decision_number == decision_number)


async def _first_matching(
    session: AsyncSession, predicate: ColumnElement[bool]
) -> DocumentRead | None:
    result = await session.execute(
        select(Document)
        .where(predicate)
        .order_by(nulls_last(Document.decision_date), Document.id)
        .limit(1)
    )
    doc = result.scalar_one_or_none()
    return DocumentRead.model_validate(doc) if doc else None


async def update(
    session: AsyncSession, document_id: uuid.UUID, dto: DocumentUpdate
) -> DocumentRead | None:
    doc = await session.get(Document, document_id)
    if doc is None:
        return None
    for field, value in dto.model_dump(exclude_none=True).items():
        setattr(doc, field, value)
    await session.flush()
    await session.refresh(doc)
    return DocumentRead.model_validate(doc)


async def list_documents(
    session: AsyncSession, skip: int = 0, limit: int = DEFAULT_PAGE_SIZE
) -> list[DocumentRead]:
    result = await session.execute(select(Document).offset(skip).limit(limit))
    return [DocumentRead.model_validate(row) for row in result.scalars()]
