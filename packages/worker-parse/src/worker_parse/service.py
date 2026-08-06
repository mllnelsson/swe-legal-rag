import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.enums import PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from shared.storage.base import StorageBackend
from shared.storage.keys import document_pdf_key
from worker_parse.parser import Parser

logger = logging.getLogger(__name__)


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

        pdf_bytes = storage.retrieve(document_pdf_key(document.id))
        raw_text = parser(pdf_bytes)
        await document_repo.update(
            session, document.id, DocumentUpdate(raw_text=raw_text)
        )
        # A scanned PDF parses to nothing without failing, and every downstream
        # step then rejects the document one at a time. Say it once, here.
        if not raw_text.strip():
            logger.warning(
                "Document %s parsed to empty text from %d bytes of PDF — "
                "likely a scan with no text layer",
                document.id,
                len(pdf_bytes),
            )
        else:
            logger.info(
                "Parsed document %s: %d characters from %d bytes of PDF",
                document.id,
                len(raw_text),
                len(pdf_bytes),
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
