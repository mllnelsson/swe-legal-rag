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
from worker_extract.extractors.factory import get_extraction_strategy
from worker_extract.services.entity_service import persist_entities
from worker_extract.services.reference_service import (
    process_references,
    reconcile_references,
)

logger = logging.getLogger(__name__)


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
    next_topic: PipelineStep = PipelineStep.CHUNK,
) -> None:
    async def body() -> None:
        document = await document_repo.get_by_id(session, document_id)
        if document is None:
            raise StepInputError(f"Document {document_id} not found")
        if document.raw_text is None:
            raise StepInputError(f"Document {document_id} has no raw text")

        strategy = get_extraction_strategy()
        result = await strategy.extract(
            document.raw_text, case_number=document.case_number
        )

        await persist_entities(
            session, entity_repo, doc_entity_repo, document_id, result.entities
        )
        await process_references(
            session,
            document_repo,
            ref_repo,
            unresolved_repo,
            document_id,
            document.case_number,
            result.references,
        )
        if document.case_number:
            await reconcile_references(
                session, unresolved_repo, ref_repo, document_id, document.case_number
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
