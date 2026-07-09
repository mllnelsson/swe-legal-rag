import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.enums import PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueuePublisher
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
    next_topic: PipelineStep = PipelineStep.METADATA,
) -> None:
    async def body() -> None:
        document = await document_repo.get_by_id(session, document_id)
        if document is None:
            raise StepInputError(f"Document {document_id} not found")
        if document.gcs_uri is None:
            raise StepInputError(f"Document {document_id} has no stored PDF")

        key = _STORAGE_KEY_TEMPLATE.format(document_id=document.id)
        pdf_bytes = storage.retrieve(key)
        raw_text = parser(pdf_bytes)
        await document_repo.update(
            session, document.id, DocumentUpdate(raw_text=raw_text)
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
