from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories.document import DocumentRepository
from shared.repositories.document_entity import DocumentEntityRepository
from shared.repositories.document_reference import DocumentReferenceRepository
from shared.repositories.entity import EntityRepository
from shared.repositories.task import TaskRepository
from shared.repositories.unresolved_reference import UnresolvedReferenceRepository
from worker_extract.extractors.factory import get_extraction_strategy
from worker_extract.services.entity_service import persist_entities
from worker_extract.services.reference_service import process_references, reconcile_references

logger = logging.getLogger(__name__)


async def process_extraction(
    document_id: UUID,
    task_id: UUID,
    document_repo: DocumentRepository,
    task_repo: TaskRepository,
    entity_repo: EntityRepository,
    doc_entity_repo: DocumentEntityRepository,
    ref_repo: DocumentReferenceRepository,
    unresolved_repo: UnresolvedReferenceRepository,
    queue_publisher: QueuePublisher,
    session: AsyncSession,
    next_topic: str = "chunk",
) -> None:
    task = await task_repo.get_by_id(task_id)
    if task is None or task.status == "completed":
        logger.info("Task %s already completed or not found, skipping", task_id)
        return

    await task_repo.update_status(task.id, TaskStatusUpdate(status="processing"))
    await session.commit()

    document = await document_repo.get_by_id(document_id)
    if document is None:
        await task_repo.update_status(
            task.id,
            TaskStatusUpdate(status="failed", error_message=f"Document {document_id} not found"),
        )
        await session.commit()
        return

    if document.raw_text is None:
        await task_repo.update_status(
            task.id,
            TaskStatusUpdate(status="failed", error_message=f"Document {document_id} has no raw text"),
        )
        await session.commit()
        return

    try:
        strategy = get_extraction_strategy()
        result = await strategy.extract(document.raw_text, case_number=document.case_number)

        await persist_entities(entity_repo, doc_entity_repo, document_id, result.entities)
        await process_references(
            document_repo,
            ref_repo,
            unresolved_repo,
            document_id,
            document.case_number,
            result.references,
        )
        if document.case_number:
            await reconcile_references(unresolved_repo, ref_repo, document_id, document.case_number)

        chunk_task = await task_repo.create(
            TaskCreate(document_id=document_id, step="chunk", status="pending")
        )
        await session.commit()
        queue_publisher.publish(
            next_topic,
            QueueMessage(task_id=chunk_task.id, document_id=document_id),
        )
        await task_repo.update_status(task.id, TaskStatusUpdate(status="completed"))
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error("Failed to process extraction for document %s: %s", document_id, exc, exc_info=True)
        await task_repo.update_status(
            task.id,
            TaskStatusUpdate(status="failed", error_message=str(exc)),
        )
        await session.commit()
