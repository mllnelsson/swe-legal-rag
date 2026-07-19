import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def get_by_case_number(
    session: AsyncSession, case_number: str
) -> DocumentRead | None:
    result = await session.execute(
        select(Document).where(Document.case_number == case_number)
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
