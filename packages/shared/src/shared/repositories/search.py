import uuid
from typing import Any, TypeVar

from sqlalchemy import Select, func, nulls_last, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from shared.dtos.document import DocumentRead
from shared.dtos.search import DocumentFacets, DocumentFilter, FacetValue
from shared.models.document import Document
from shared.models.document_entity import DocumentEntity
from shared.models.document_reference import DocumentReference
from shared.models.entity import Entity

# How many distinct values a single facet reports. `category` and
# `decision_outcome` are free text lifted off the PDFs, so their cardinality is
# unbounded in principle; the cap keeps the response a browsable vocabulary
# rather than a dump.
MAX_FACET_VALUES = 50

_SelectT = TypeVar("_SelectT", bound=Select[Any])


def _apply_document_filter(stmt: _SelectT, document_filter: DocumentFilter) -> _SelectT:
    """Narrow a statement over ``documents`` to those matching the filter.

    Also gates on ``raw_text IS NOT NULL`` — a document that has not been parsed
    yet has no metadata to match on and no chunks to retrieve, so it is not
    searchable in any meaningful sense. Every caller wants that gate, so it lives
    here rather than at each call site where the two could drift apart.
    """
    stmt = stmt.where(Document.raw_text.isnot(None))

    if document_filter.date_from is not None:
        stmt = stmt.where(Document.decision_date >= document_filter.date_from)
    if document_filter.date_to is not None:
        stmt = stmt.where(Document.decision_date <= document_filter.date_to)
    if document_filter.category is not None:
        stmt = stmt.where(Document.category.ilike(f"%{document_filter.category}%"))
    if document_filter.decision_outcome is not None:
        stmt = stmt.where(
            Document.decision_outcome.ilike(f"%{document_filter.decision_outcome}%")
        )
    if document_filter.case_number is not None:
        stmt = stmt.where(Document.case_number == document_filter.case_number)
    if document_filter.decision_number is not None:
        stmt = stmt.where(Document.decision_number == document_filter.decision_number)

    if document_filter.entity_names or document_filter.entity_types:
        entity_sub = select(DocumentEntity.document_id).join(
            Entity, DocumentEntity.entity_id == Entity.id
        )
        if document_filter.entity_names:
            name_conditions = [
                Entity.name.ilike(f"%{name}%") for name in document_filter.entity_names
            ]
            entity_sub = entity_sub.where(or_(*name_conditions))
        if document_filter.entity_types:
            entity_sub = entity_sub.where(Entity.type.in_(document_filter.entity_types))
        stmt = stmt.where(Document.id.in_(entity_sub))

    if document_filter.references_case_number is not None:
        ref_doc_sub = select(Document.id).where(
            Document.case_number == document_filter.references_case_number
        )
        related_as_target = select(DocumentReference.source_document_id).where(
            DocumentReference.target_document_id.in_(ref_doc_sub)
        )
        related_as_source = select(DocumentReference.target_document_id).where(
            DocumentReference.source_document_id.in_(ref_doc_sub)
        )
        stmt = stmt.where(
            or_(Document.id.in_(related_as_target), Document.id.in_(related_as_source))
        )

    return stmt


async def find_candidate_documents(
    session: AsyncSession,
    document_filter: DocumentFilter,
    limit: int | None = None,
) -> list[uuid.UUID]:
    stmt = _apply_document_filter(select(Document.id), document_filter)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars())


async def list_filtered_documents(
    session: AsyncSession,
    document_filter: DocumentFilter,
    *,
    limit: int,
    offset: int = 0,
    newest_first: bool = True,
) -> list[DocumentRead]:
    """Browse documents by metadata alone, without a search query."""
    stmt = _apply_document_filter(select(Document), document_filter)
    decision_date_order = (
        Document.decision_date.desc() if newest_first else Document.decision_date.asc()
    )
    # `decision_date` is nullable and `id` breaks ties, so a document cannot shift
    # between pages while the caller is paging through them.
    stmt = (
        stmt.order_by(nulls_last(decision_date_order), Document.id)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [DocumentRead.model_validate(row) for row in result.scalars()]


async def count_filtered_documents(
    session: AsyncSession, document_filter: DocumentFilter
) -> int:
    stmt = _apply_document_filter(
        select(func.count()).select_from(Document), document_filter
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def _column_facet(
    session: AsyncSession, column: InstrumentedAttribute[str | None]
) -> list[FacetValue]:
    stmt = (
        select(column, func.count().label("value_count"))
        .select_from(Document)
        .where(Document.raw_text.isnot(None), column.isnot(None))
        .group_by(column)
        .order_by(func.count().desc(), column)
        .limit(MAX_FACET_VALUES)
    )
    result = await session.execute(stmt)
    return [FacetValue(value=value, count=count) for value, count in result.all()]


async def _entity_type_facet(session: AsyncSession) -> list[FacetValue]:
    # Counts documents, not entities: "how many decisions can this type narrow to"
    # is the question a filter vocabulary answers.
    stmt = (
        select(Entity.type, func.count(func.distinct(DocumentEntity.document_id)))
        .select_from(Entity)
        .join(DocumentEntity, DocumentEntity.entity_id == Entity.id)
        .group_by(Entity.type)
        .order_by(func.count(func.distinct(DocumentEntity.document_id)).desc())
    )
    result = await session.execute(stmt)
    return [FacetValue(value=value, count=count) for value, count in result.all()]


async def get_facets(session: AsyncSession) -> DocumentFacets:
    """The values the metadata filters will actually match.

    Scoped to the same population `_apply_document_filter` searches, so a value
    reported here always matches at least one document.
    """
    categories = await _column_facet(session, Document.category)
    outcomes = await _column_facet(session, Document.decision_outcome)
    entity_types = await _entity_type_facet(session)

    range_stmt = select(
        func.min(Document.decision_date),
        func.max(Document.decision_date),
        func.count(),
    ).where(Document.raw_text.isnot(None))
    earliest, latest, document_count = (await session.execute(range_stmt)).one()

    return DocumentFacets(
        categories=categories,
        decision_outcomes=outcomes,
        entity_types=entity_types,
        earliest_decision_date=earliest,
        latest_decision_date=latest,
        document_count=document_count,
    )
