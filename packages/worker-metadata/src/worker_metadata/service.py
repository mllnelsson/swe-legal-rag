from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.enums import PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueuePublisher
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
    async def body() -> None:
        document = await document_repo.get_by_id(session, document_id)
        if document is None:
            raise StepInputError(f"Document {document_id} not found")
        if document.raw_text is None:
            raise StepInputError(f"Document {document_id} has no raw text")

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

    await run_pipeline_step(
        task_repo=task_repo,
        session=session,
        task_id=task_id,
        document_id=document_id,
        next_step=next_topic,
        queue_publisher=queue_publisher,
        body=body,
    )
