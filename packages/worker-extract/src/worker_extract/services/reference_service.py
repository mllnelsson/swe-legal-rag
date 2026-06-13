from __future__ import annotations

from uuid import UUID

from shared.dtos.document_reference import DocumentReferenceCreate
from shared.dtos.unresolved_reference import UnresolvedReferenceCreate
from shared.repositories.document import DocumentRepository
from shared.repositories.document_reference import DocumentReferenceRepository
from shared.repositories.unresolved_reference import UnresolvedReferenceRepository
from worker_extract.models import ExtractedReference


async def process_references(
    doc_repo: DocumentRepository,
    ref_repo: DocumentReferenceRepository,
    unresolved_repo: UnresolvedReferenceRepository,
    source_document_id: UUID,
    source_case_number: str | None,
    references: list[ExtractedReference],
) -> None:
    for ref in references:
        if source_case_number and ref.case_number == source_case_number:
            continue
        target = await doc_repo.get_by_case_number(ref.case_number)
        if target is not None:
            await ref_repo.upsert(
                DocumentReferenceCreate(
                    source_document_id=source_document_id,
                    target_document_id=target.id,
                    reference_context=ref.reference_context,
                )
            )
        else:
            await unresolved_repo.upsert(
                UnresolvedReferenceCreate(
                    source_document_id=source_document_id,
                    target_case_number=ref.case_number,
                    reference_context=ref.reference_context,
                )
            )


async def reconcile_references(
    unresolved_repo: UnresolvedReferenceRepository,
    ref_repo: DocumentReferenceRepository,
    document_id: UUID,
    case_number: str,
) -> int:
    unresolved = await unresolved_repo.get_by_target_case_number(case_number)
    count = 0
    for ur in unresolved:
        await ref_repo.upsert(
            DocumentReferenceCreate(
                source_document_id=ur.source_document_id,
                target_document_id=document_id,
                reference_context=ur.reference_context,
            )
        )
        await unresolved_repo.delete(ur.id)
        count += 1
    return count
