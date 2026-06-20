import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.search import DocumentFilter
from shared.models.document import Document
from shared.models.document_entity import DocumentEntity
from shared.models.document_reference import DocumentReference
from shared.models.entity import Entity


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_candidate_documents(self, filter: DocumentFilter) -> list[uuid.UUID]:
        stmt = select(Document.id).where(Document.raw_text.isnot(None))

        if filter.date_from is not None:
            stmt = stmt.where(Document.decision_date >= filter.date_from)
        if filter.date_to is not None:
            stmt = stmt.where(Document.decision_date <= filter.date_to)
        if filter.category is not None:
            stmt = stmt.where(Document.category.ilike(f"%{filter.category}%"))
        if filter.decision_outcome is not None:
            stmt = stmt.where(Document.decision_outcome.ilike(f"%{filter.decision_outcome}%"))

        if filter.entity_names or filter.entity_types:
            entity_sub = select(DocumentEntity.document_id).join(
                Entity, DocumentEntity.entity_id == Entity.id
            )
            if filter.entity_names:
                name_conditions = [Entity.name.ilike(f"%{name}%") for name in filter.entity_names]
                entity_sub = entity_sub.where(or_(*name_conditions))
            if filter.entity_types:
                entity_sub = entity_sub.where(Entity.type.in_(filter.entity_types))
            stmt = stmt.where(Document.id.in_(entity_sub))

        if filter.references_case_number is not None:
            ref_doc_sub = select(Document.id).where(
                Document.case_number == filter.references_case_number
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

        result = await self._session.execute(stmt)
        return list(result.scalars())
