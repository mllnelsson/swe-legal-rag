from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai import CountTokens, summarize_document
from agent_kit.llm import LLMProvider
from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentUpdate
from shared.enums import PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueuePublisher
from shared.repositories import ChunkRepo, DocumentRepo, TaskRepo
from shared.segmentation import split_document
from worker_chunk.budget import ChunkBudget
from worker_chunk.chunker import (
    build_contextual_text,
    split_document_into_chunks,
    truncate_summary,
)

logger = logging.getLogger(__name__)


async def process_chunking(
    document_id: UUID,
    task_id: UUID,
    document_repo: DocumentRepo,
    chunk_repo: ChunkRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    session: AsyncSession,
    count_tokens: CountTokens,
    budget: ChunkBudget,
    next_topic: PipelineStep = PipelineStep.EMBED,
    llm_provider: LLMProvider | None = None,
) -> None:
    """Summarise a document and split it into embeddable chunks.

    `count_tokens` and `budget` have no defaults. Both describe the embedding
    model's window — the limit that decides whether a chunk survives embedding
    intact — and a default here would be a ruler unrelated to the model actually
    in use. Build them together with `ai.create_embedding_ruler` and
    `worker_chunk.budget.compute_chunk_budget`.
    """

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

        # One summary value, stored and prepended. Truncating only on the way into
        # contextual_text would leave documents.summary claiming a text that was
        # never embedded.
        summary = truncate_summary(
            result.summary,
            count_tokens=count_tokens,
            max_tokens=budget.summary_reserve_tokens,
        )
        if summary != result.summary:
            logger.warning(
                "Summary for document %s was %d tokens and has been cut to the "
                "%d-token reserve — the summarisation prompt is not holding",
                document_id,
                count_tokens(result.summary),
                budget.summary_reserve_tokens,
            )

        await document_repo.update(
            session, document_id, DocumentUpdate(summary=summary)
        )

        chunks = split_document_into_chunks(
            segments, count_tokens=count_tokens, budget=budget
        )

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

        # A sentence longer than the whole budget is emitted as its own chunk
        # rather than cut mid-thought, so the chunker can hand back text the
        # embedding model will truncate. Reported here, where the document is in
        # scope, to keep the chunker a pure function.
        for dto in chunk_dtos:
            if count_tokens(dto.chunk_text) > budget.max_tokens:
                logger.warning(
                    "Chunk %d of document %s is %d tokens, over the %d-token "
                    "budget — its tail will be dropped when embedded",
                    dto.chunk_index,
                    document_id,
                    count_tokens(dto.chunk_text),
                    budget.max_tokens,
                )

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
