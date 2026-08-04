import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Row, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from shared.dtos.document_reference import (
    DocumentReferenceCreate,
    DocumentReferenceRead,
    ReferenceEdge,
    ReferenceEdges,
)
from shared.models.document import Document
from shared.models.document_reference import DocumentReference
from shared.source_headline import headline_title


async def create(
    session: AsyncSession, dto: DocumentReferenceCreate
) -> DocumentReferenceRead:
    ref = DocumentReference(
        source_document_id=dto.source_document_id,
        target_document_id=dto.target_document_id,
        reference_context=dto.reference_context,
    )
    session.add(ref)
    await session.flush()
    await session.refresh(ref)
    return DocumentReferenceRead.model_validate(ref)


async def upsert(
    session: AsyncSession, dto: DocumentReferenceCreate
) -> DocumentReferenceRead:
    result = await session.execute(
        select(DocumentReference).where(
            DocumentReference.source_document_id == dto.source_document_id,
            DocumentReference.target_document_id == dto.target_document_id,
        )
    )
    ref = result.scalar_one_or_none()
    if ref is None:
        ref = DocumentReference(
            source_document_id=dto.source_document_id,
            target_document_id=dto.target_document_id,
            reference_context=dto.reference_context,
        )
        session.add(ref)
        await session.flush()
        await session.refresh(ref)
    return DocumentReferenceRead.model_validate(ref)


async def get_by_source_document_id(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentReferenceRead]:
    result = await session.execute(
        select(DocumentReference).where(
            DocumentReference.source_document_id == document_id
        )
    )
    return [DocumentReferenceRead.model_validate(row) for row in result.scalars()]


async def get_by_target_document_id(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentReferenceRead]:
    result = await session.execute(
        select(DocumentReference).where(
            DocumentReference.target_document_id == document_id
        )
    )
    return [DocumentReferenceRead.model_validate(row) for row in result.scalars()]


def _to_reference_edges(rows: Sequence[Row[Any]]) -> list[ReferenceEdge]:
    return [
        ReferenceEdge(
            document_id=document_id,
            case_number=case_number,
            decision_number=decision_number,
            decision_date=decision_date,
            headline=headline_title(headline),
            reference_context=reference_context,
        )
        for (
            document_id,
            case_number,
            decision_number,
            decision_date,
            headline,
            reference_context,
        ) in rows
    ]


async def _resolved_edges(
    session: AsyncSession,
    *,
    join_on: InstrumentedAttribute[uuid.UUID],
    match_on: InstrumentedAttribute[uuid.UUID],
    document_id: uuid.UUID,
) -> list[ReferenceEdge]:
    """Citations joined to the document on the *other* end of the edge."""
    stmt = (
        select(
            Document.id,
            Document.case_number,
            Document.decision_number,
            Document.decision_date,
            Document.source_headline,
            DocumentReference.reference_context,
        )
        .select_from(DocumentReference)
        .join(Document, join_on == Document.id)
        .where(match_on == document_id)
        .order_by(nulls_last(Document.decision_date.desc()), Document.id)
    )
    result = await session.execute(stmt)
    return _to_reference_edges(result.all())


async def list_references_for_document(
    session: AsyncSession, document_id: uuid.UUID
) -> ReferenceEdges:
    """Both directions of this document's citations, one hop out.

    Resolved in two queries rather than by looking each edge's counterpart up
    individually, since the detail view renders every edge as a link.
    """
    outgoing = await _resolved_edges(
        session,
        join_on=DocumentReference.target_document_id,
        match_on=DocumentReference.source_document_id,
        document_id=document_id,
    )
    incoming = await _resolved_edges(
        session,
        join_on=DocumentReference.source_document_id,
        match_on=DocumentReference.target_document_id,
        document_id=document_id,
    )
    return ReferenceEdges(outgoing=outgoing, incoming=incoming)
