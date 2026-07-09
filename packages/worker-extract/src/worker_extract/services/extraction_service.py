from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
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
    task = await task_repo.get_by_id(session, task_id)
    if task is None or task.status == TaskStatus.COMPLETED:
        logger.info("Task %s already completed or not found, skipping", task_id)
        return

    await task_repo.update_status(
        session, task.id, TaskStatusUpdate(status=TaskStatus.PROCESSING)
    )
    await session.commit()

    document = await document_repo.get_by_id(session, document_id)
    if document is None:
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(
                status=TaskStatus.FAILED,
                error_message=f"Document {document_id} not found",
            ),
        )
        await session.commit()
        return

    if document.raw_text is None:
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(
                status=TaskStatus.FAILED,
                error_message=f"Document {document_id} has no raw text",
            ),
        )
        await session.commit()
        return

    try:
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

        chunk_task = await task_repo.create(
            session,
            TaskCreate(
                document_id=document_id,
                step=PipelineStep.CHUNK,
                status=TaskStatus.PENDING,
            ),
        )
        await session.commit()
        queue_publisher.publish(
            next_topic,
            QueueMessage(task_id=chunk_task.id, document_id=document_id),
        )
        await task_repo.update_status(
            session, task.id, TaskStatusUpdate(status=TaskStatus.COMPLETED)
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error(
            "Failed to process extraction for document %s: %s",
            document_id,
            exc,
            exc_info=True,
        )
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(status=TaskStatus.FAILED, error_message=str(exc)),
        )
        await session.commit()
