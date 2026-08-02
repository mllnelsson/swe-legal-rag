from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueuePublisher
from shared.repositories import (
    DocumentEntityRepo,
    DocumentReferenceRepo,
    DocumentRepo,
    EntityRepo,
    TaskRepo,
    UnresolvedReferenceRepo,
)
from shared.segmentation import split_document
from worker_extract.extractors.base import ExtractionStrategy
from worker_extract.services.entity_service import persist_entities
from worker_extract.services.reference_service import (
    process_references,
    reconcile_references,
)

logger = logging.getLogger(__name__)


def _own_identifiers(*identifiers: str | None) -> list[str]:
    """The identifiers by which this document refers to itself.

    A decision carries both an ärendenummer and a beslutsnummer; a citation in
    either space that matches one of them is a self-reference, not a cross-reference.
    """
    return [identifier for identifier in identifiers if identifier]


async def process_extraction(
    document_id: UUID,
    task_id: UUID,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    entity_repo: EntityRepo,
    doc_entity_repo: DocumentEntityRepo,
    ref_repo: DocumentReferenceRepo,
    unresolved_repo: UnresolvedReferenceRepo,
    queue_publisher: QueuePublisher,
    session: AsyncSession,
    strategy: ExtractionStrategy,
    next_topic: PipelineStep = PipelineStep.CHUNK,
) -> None:
    """Extract entities and references from one document.

    `strategy` is injected rather than looked up here: two of the three modes
    construct an LLM provider, and building one per document is what a
    factory call inside the step body used to do. Every other worker builds its
    provider once at startup and passes it in.
    """

    async def body() -> None:
        document = await document_repo.get_by_id(session, document_id)
        if document is None:
            raise StepInputError(f"Document {document_id} not found")
        if document.raw_text is None:
            raise StepInputError(f"Document {document_id} has no raw text")

        segments = split_document(document.raw_text)
        result = await strategy(segments, document.case_number)

        await persist_entities(
            session, entity_repo, doc_entity_repo, document_id, result.entities
        )
        await process_references(
            session,
            document_repo,
            ref_repo,
            unresolved_repo,
            document_id,
            _own_identifiers(document.case_number, document.decision_number),
            result.references,
        )
        await reconcile_references(
            session,
            unresolved_repo,
            ref_repo,
            document_id,
            _own_identifiers(document.case_number, document.decision_number),
        )

    await run_pipeline_step(
        task_repo=task_repo,
        session=session,
        task_id=task_id,
        document_id=document_id,
        next_step=next_topic,
        queue_publisher=queue_publisher,
        body=body,
    )
