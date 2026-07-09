from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from worker_metadata.patterns import MetadataResult, is_complete

logger = logging.getLogger(__name__)

_METADATA_FIELDS = ("case_number", "decision_date", "decision_outcome", "category")


async def process_metadata(
    document_id: UUID,
    task_id: UUID,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    rule_extractor: Callable[[str], MetadataResult],
    llm_extractor: Callable[[str, list[str]], Awaitable[MetadataResult]],
    session: AsyncSession,
    next_topic: PipelineStep = PipelineStep.EXTRACT,
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
        result = rule_extractor(document.raw_text)

        if not is_complete(result):
            missing = [f for f in _METADATA_FIELDS if getattr(result, f) is None]
            logger.info(
                "Document %s: rule-based incomplete, LLM fallback for fields: %s",
                document_id,
                missing,
            )
            try:
                llm_result = await llm_extractor(document.raw_text, missing)
                for field in missing:
                    llm_value = getattr(llm_result, field)
                    if llm_value is not None:
                        setattr(result, field, llm_value)
            except Exception as exc:
                logger.warning(
                    "LLM extraction failed for document %s: %s", document_id, exc
                )

        await document_repo.update(
            session,
            document.id,
            DocumentUpdate(
                case_number=result.case_number,
                decision_date=result.decision_date,
                decision_outcome=result.decision_outcome,
                category=result.category,
            ),
        )
        extract_task = await task_repo.create(
            session,
            TaskCreate(
                document_id=document.id,
                step=PipelineStep.EXTRACT,
                status=TaskStatus.PENDING,
            ),
        )
        await session.commit()
        queue_publisher.publish(
            next_topic,
            QueueMessage(task_id=extract_task.id, document_id=document.id),
        )
        await task_repo.update_status(
            session, task.id, TaskStatusUpdate(status=TaskStatus.COMPLETED)
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error("Failed to process metadata for document %s: %s", document_id, exc)
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(status=TaskStatus.FAILED, error_message=str(exc)),
        )
        await session.commit()
