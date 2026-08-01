"""Route extracted citations to resolved or unresolved reference rows.

Decisions cite each other by ärendenummer ("2025-0017") or by beslutsnummer
("13/2025"), and a document carries both. The two canonical formats are disjoint,
so a reference string says for itself which column can resolve it — no separate
"kind" needs to travel with it from the extractor.

A citation the corpus does not contain yet is parked in `unresolved_references`
and promoted later, when the cited decision is itself ingested.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentRead
from shared.dtos.document_reference import DocumentReferenceCreate
from shared.dtos.unresolved_reference import UnresolvedReferenceCreate
from shared.repositories import (
    DocumentReferenceRepo,
    DocumentRepo,
    UnresolvedReferenceRepo,
)
from ai.dtos import ExtractedReference

# Beslutsnummer are written "N/YYYY"; ärendenummer never contain a slash.
_DECISION_NUMBER_MARKER = "/"


async def process_references(
    session: AsyncSession,
    doc_repo: DocumentRepo,
    ref_repo: DocumentReferenceRepo,
    unresolved_repo: UnresolvedReferenceRepo,
    source_document_id: UUID,
    source_identifiers: list[str],
    references: list[ExtractedReference],
) -> None:
    for ref in references:
        if ref.case_number in source_identifiers:
            continue
        target = await _resolve(session, doc_repo, ref.case_number)
        if target is not None:
            await ref_repo.upsert(
                session,
                DocumentReferenceCreate(
                    source_document_id=source_document_id,
                    target_document_id=target.id,
                    reference_context=ref.reference_context,
                ),
            )
        else:
            await unresolved_repo.upsert(
                session,
                UnresolvedReferenceCreate(
                    source_document_id=source_document_id,
                    target_case_number=ref.case_number,
                    reference_context=ref.reference_context,
                ),
            )


async def reconcile_references(
    session: AsyncSession,
    unresolved_repo: UnresolvedReferenceRepo,
    ref_repo: DocumentReferenceRepo,
    document_id: UUID,
    identifiers: list[str],
) -> int:
    """Promote references parked under any identifier this document answers to."""
    count = 0
    for identifier in identifiers:
        unresolved = await unresolved_repo.get_by_target_case_number(
            session, identifier
        )
        for row in unresolved:
            # A document that somehow cited itself must not become a self-edge:
            # document_references has a composite PK over (source, target).
            if row.source_document_id == document_id:
                await unresolved_repo.delete(session, row.id)
                continue
            await ref_repo.upsert(
                session,
                DocumentReferenceCreate(
                    source_document_id=row.source_document_id,
                    target_document_id=document_id,
                    reference_context=row.reference_context,
                ),
            )
            await unresolved_repo.delete(session, row.id)
            count += 1
    return count


async def _resolve(
    session: AsyncSession, doc_repo: DocumentRepo, identifier: str
) -> DocumentRead | None:
    if _DECISION_NUMBER_MARKER in identifier:
        return await doc_repo.get_by_decision_number(session, identifier)
    return await doc_repo.get_by_case_number(session, identifier)
