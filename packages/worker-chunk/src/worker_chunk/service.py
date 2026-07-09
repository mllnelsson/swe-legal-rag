from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai import summarize_document
from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentUpdate
from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import ChunkRepo, DocumentRepo, TaskRepo

from worker_chunk.chunker import build_contextual_text, split_into_chunks

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = (
    "Summarize this Swedish legal decision in 2-3 sentences. "
    "Focus on the legal issue, the ruling, and the key reasoning."
)


async def process_chunking(
    document_id: UUID,
    task_id: UUID,
    document_repo: DocumentRepo,
    chunk_repo: ChunkRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    session: AsyncSession,
    next_topic: PipelineStep = PipelineStep.EMBED,
) -> None:
    task = await task_repo.get_by_id(session, task_id)
    if task is None or task.status == TaskStatus.COMPLETED:
        logger.info("Task %s already completed or not found, skipping", task_id)
        return

    await task_repo.update_status(
        session, task_id, TaskStatusUpdate(status=TaskStatus.PROCESSING)
    )
    await session.commit()

    document = await document_repo.get_by_id(session, document_id)
    if document is None:
        await task_repo.update_status(
            session,
            task_id,
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
            task_id,
            TaskStatusUpdate(
                status=TaskStatus.FAILED,
                error_message=f"Document {document_id} has no raw text",
            ),
        )
        await session.commit()
        return

    try:
        result = await summarize_document(document.raw_text)
        summary = result.summary

        await document_repo.update(
            session, document_id, DocumentUpdate(summary=summary)
        )

        chunk_texts = split_into_chunks(document.raw_text)

        await chunk_repo.delete_by_document_id(session, document_id)

        chunk_dtos = [
            ChunkCreate(
                document_id=document_id,
                chunk_index=i,
                chunk_text=chunk_text,
                contextual_text=build_contextual_text(summary, chunk_text),
            )
            for i, chunk_text in enumerate(chunk_texts)
        ]

        if chunk_dtos:
            await chunk_repo.bulk_create(session, chunk_dtos)

        embed_task = await task_repo.create(
            session,
            TaskCreate(
                document_id=document_id,
                step=PipelineStep.EMBED,
                status=TaskStatus.PENDING,
            ),
        )
        await session.commit()

        queue_publisher.publish(
            next_topic,
            QueueMessage(task_id=embed_task.id, document_id=document_id),
        )

        await task_repo.update_status(
            session, task_id, TaskStatusUpdate(status=TaskStatus.COMPLETED)
        )
        await session.commit()

        logger.info(
            "Chunked document %s into %d chunks, published to %s",
            document_id,
            len(chunk_dtos),
            next_topic,
        )

    except Exception as exc:
        await session.rollback()
        logger.error("Failed to chunk document %s: %s", document_id, exc, exc_info=True)
        await task_repo.update_status(
            session,
            task_id,
            TaskStatusUpdate(status=TaskStatus.FAILED, error_message=str(exc)),
        )
        await session.commit()
        raise
