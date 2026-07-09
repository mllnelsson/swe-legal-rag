import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from shared.storage.base import StorageBackend
from worker_parse.parser import Parser

logger = logging.getLogger(__name__)

_STORAGE_KEY_TEMPLATE = "documents/{document_id}/original.pdf"


async def process_parse(
    document_id: UUID,
    task_id: UUID,
    storage: StorageBackend,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    parser: Parser,
    session: AsyncSession,
    next_topic: str = "metadata",
) -> None:
    task = await task_repo.get_by_id(session, task_id)
    if task is None or task.status == "completed":
        logger.info("Task %s already completed or not found, skipping", task_id)
        return

    await task_repo.update_status(
        session, task.id, TaskStatusUpdate(status="processing")
    )
    await session.commit()

    document = await document_repo.get_by_id(session, document_id)
    if document is None:
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(
                status="failed", error_message=f"Document {document_id} not found"
            ),
        )
        await session.commit()
        return

    if document.gcs_uri is None:
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(
                status="failed",
                error_message=f"Document {document_id} has no stored PDF",
            ),
        )
        await session.commit()
        return

    try:
        key = _STORAGE_KEY_TEMPLATE.format(document_id=document.id)
        pdf_bytes = storage.retrieve(key)
        raw_text = parser(pdf_bytes)
        await document_repo.update(
            session, document.id, DocumentUpdate(raw_text=raw_text)
        )
        metadata_task = await task_repo.create(
            session,
            TaskCreate(document_id=document.id, step="metadata", status="pending"),
        )
        await session.commit()
        queue_publisher.publish(
            next_topic,
            QueueMessage(task_id=metadata_task.id, document_id=document.id),
        )
        await task_repo.update_status(
            session, task.id, TaskStatusUpdate(status="completed")
        )
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error("Failed to parse document %s: %s", document.id, e)
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(status="failed", error_message=str(e)),
        )
        await session.commit()
