from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai import summarize_document
from llm_core import LLMProvider
from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentUpdate
from shared.enums import PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueuePublisher
from shared.repositories import ChunkRepo, DocumentRepo, TaskRepo
from shared.segmentation import split_document
from worker_chunk.chunker import build_contextual_text, split_document_into_chunks

logger = logging.getLogger(__name__)


async def process_chunking(
    document_id: UUID,
    task_id: UUID,
    document_repo: DocumentRepo,
    chunk_repo: ChunkRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    session: AsyncSession,
    next_topic: PipelineStep = PipelineStep.EMBED,
    llm_provider: LLMProvider | None = None,
) -> None:
    async def body() -> None:
        document = await document_repo.get_by_id(session, document_id)
        if document is None:
            raise StepInputError(f"Document {document_id} not found")
        if document.raw_text is None:
            raise StepInputError(f"Document {document_id} has no raw text")

        segments = split_document(document.raw_text)

        # Body only: the summary describes what Överklagandenämnden decided, and it
        # is prepended to every chunk's contextual_text, so an appendix-derived
        # summary would leak the appealed decision into every embedding.
        result = await summarize_document(segments.body, provider=llm_provider)
        summary = result.summary

        await document_repo.update(
            session, document_id, DocumentUpdate(summary=summary)
        )

        chunks = split_document_into_chunks(segments)

        await chunk_repo.delete_by_document_id(session, document_id)

        chunk_dtos = [
            ChunkCreate(
                document_id=document_id,
                chunk_index=i,
                chunk_text=chunk.text,
                contextual_text=build_contextual_text(summary, chunk.text),
                section=chunk.section,
                appendix_label=chunk.appendix_label,
            )
            for i, chunk in enumerate(chunks)
        ]

        if chunk_dtos:
            await chunk_repo.bulk_create(session, chunk_dtos)

        logger.info("Chunked document %s into %d chunks", document_id, len(chunk_dtos))

    await run_pipeline_step(
        task_repo=task_repo,
        session=session,
        task_id=task_id,
        document_id=document_id,
        next_step=next_topic,
        queue_publisher=queue_publisher,
        body=body,
        reraise=True,
    )
