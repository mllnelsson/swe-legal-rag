import uuid

from sqlalchemy import case, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document_entity import (
    DocumentEntityCreate,
    DocumentEntityDetail,
    DocumentEntityRead,
    EntityDocumentRef,
)
from shared.enums import EntityRelevance
from shared.models.document import Document
from shared.models.document_entity import DocumentEntity
from shared.models.entity import Entity
from shared.source_headline import headline_title

# Primary entities carry the holding, so they lead; alphabetical ordering would
# put "mentioned" first and bury them.
_PRIMARY_FIRST = case((DocumentEntity.relevance == EntityRelevance.PRIMARY, 0), else_=1)


async def create(
    session: AsyncSession, dto: DocumentEntityCreate
) -> DocumentEntityRead:
    de = DocumentEntity(
        document_id=dto.document_id, entity_id=dto.entity_id, relevance=dto.relevance
    )
    session.add(de)
    await session.flush()
    await session.refresh(de)
    return DocumentEntityRead.model_validate(de)


async def get_by_document_id(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentEntityRead]:
    result = await session.execute(
        select(DocumentEntity).where(DocumentEntity.document_id == document_id)
    )
    return [DocumentEntityRead.model_validate(row) for row in result.scalars()]


async def upsert(
    session: AsyncSession, dto: DocumentEntityCreate
) -> DocumentEntityRead:
    result = await session.execute(
        select(DocumentEntity).where(
            DocumentEntity.document_id == dto.document_id,
            DocumentEntity.entity_id == dto.entity_id,
        )
    )
    de = result.scalar_one_or_none()
    if de is None:
        de = DocumentEntity(
            document_id=dto.document_id,
            entity_id=dto.entity_id,
            relevance=dto.relevance,
        )
        session.add(de)
        await session.flush()
        await session.refresh(de)
    elif dto.relevance == EntityRelevance.PRIMARY and (
        de.relevance != EntityRelevance.PRIMARY
    ):
        de.relevance = EntityRelevance.PRIMARY
        await session.flush()
        await session.refresh(de)
    return DocumentEntityRead.model_validate(de)


async def get_by_entity_id(
    session: AsyncSession, entity_id: uuid.UUID
) -> list[DocumentEntityRead]:
    result = await session.execute(
        select(DocumentEntity).where(DocumentEntity.entity_id == entity_id)
    )
    return [DocumentEntityRead.model_validate(row) for row in result.scalars()]


async def list_entities_for_document(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentEntityDetail]:
    """This document's entities, resolved to names and types."""
    stmt = (
        select(Entity.id, Entity.name, Entity.type, DocumentEntity.relevance)
        .select_from(DocumentEntity)
        .join(Entity, DocumentEntity.entity_id == Entity.id)
        .where(DocumentEntity.document_id == document_id)
        .order_by(_PRIMARY_FIRST, Entity.type, Entity.name)
    )
    result = await session.execute(stmt)
    return [
        DocumentEntityDetail(
            entity_id=entity_id, name=name, type=entity_type, relevance=relevance
        )
        for entity_id, name, entity_type, relevance in result.all()
    ]


async def list_documents_for_entity(
    session: AsyncSession,
    entity_id: uuid.UUID,
    *,
    relevance: str | None = None,
    limit: int,
    offset: int = 0,
) -> list[EntityDocumentRef]:
    """Documents carrying this entity — the reverse hop through the graph."""
    stmt = (
        select(
            Document.id,
            Document.case_number,
            Document.decision_number,
            Document.decision_date,
            Document.source_headline,
            Document.category,
            Document.decision_outcome,
            DocumentEntity.relevance,
        )
        .select_from(DocumentEntity)
        .join(Document, DocumentEntity.document_id == Document.id)
        .where(DocumentEntity.entity_id == entity_id)
    )
    if relevance is not None:
        stmt = stmt.where(DocumentEntity.relevance == relevance)
    stmt = (
        stmt.order_by(
            _PRIMARY_FIRST, nulls_last(Document.decision_date.desc()), Document.id
        )
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [
        EntityDocumentRef(
            document_id=document_id,
            case_number=case_number,
            decision_number=decision_number,
            decision_date=decision_date,
            headline=headline_title(headline),
            category=category,
            decision_outcome=decision_outcome,
            relevance=edge_relevance,
        )
        for (
            document_id,
            case_number,
            decision_number,
            decision_date,
            headline,
            category,
            decision_outcome,
            edge_relevance,
        ) in result.all()
    ]


async def count_documents_for_entity(
    session: AsyncSession, entity_id: uuid.UUID, *, relevance: str | None = None
) -> int:
    stmt = (
        select(func.count())
        .select_from(DocumentEntity)
        .where(DocumentEntity.entity_id == entity_id)
    )
    if relevance is not None:
        stmt = stmt.where(DocumentEntity.relevance == relevance)
    result = await session.execute(stmt)
    return result.scalar_one()
