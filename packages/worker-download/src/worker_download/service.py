import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from shared.storage.base import StorageBackend
from worker_download.errors import DownloadError

logger = logging.getLogger(__name__)

_USER_AGENT = "church-legal-db/1.0 (PDF downloader)"

# Retry only on 5xx: below this the server rejected the request itself (4xx) and
# a retry would not help.
HTTP_SERVER_ERROR = 500
# Exponential backoff base: sleep BACKOFF_BASE_SECONDS ** attempt between retries.
BACKOFF_BASE_SECONDS = 2
# Always make at least one attempt, even if max_retries is misconfigured to <1.
MIN_ATTEMPTS = 1


def _download_pdf(url: str, timeout: int, max_retries: int) -> bytes:
    last_error: Exception = DownloadError(f"No attempts made for {url}")
    headers = {"User-Agent": _USER_AGENT}
    with httpx.Client(timeout=timeout, headers=headers) as client:
        for attempt in range(max(MIN_ATTEMPTS, max_retries)):
            try:
                response = client.get(url)
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as e:
                if e.response.status_code < HTTP_SERVER_ERROR:
                    raise
                last_error = e
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
            if attempt < max_retries - 1:
                time.sleep(BACKOFF_BASE_SECONDS**attempt)
    raise last_error


async def process_download(
    message: QueueMessage,
    *,
    session: AsyncSession,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    storage: StorageBackend,
    queue_publisher: QueuePublisher,
    timeout: int,
    max_retries: int,
    rate_limit_delay: float,
    next_topic: PipelineStep,
) -> None:
    task = await task_repo.get_by_id(session, message.task_id)
    if task is None or task.status == TaskStatus.COMPLETED:
        logger.info("Task %s already completed or not found, skipping", message.task_id)
        return

    await task_repo.update_status(
        session, task.id, TaskStatusUpdate(status=TaskStatus.PROCESSING)
    )
    await session.commit()

    document = await document_repo.get_by_id(session, message.document_id)
    if document is None:
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(
                status=TaskStatus.FAILED,
                error_message=f"Document {message.document_id} not found",
            ),
        )
        await session.commit()
        return

    if document.gcs_uri is not None:
        parse_task = await task_repo.create(
            session,
            TaskCreate(
                document_id=document.id,
                step=PipelineStep.PARSE,
                status=TaskStatus.PENDING,
            ),
        )
        await session.commit()
        queue_publisher.publish(
            next_topic,
            QueueMessage(task_id=parse_task.id, document_id=document.id),
        )
        await task_repo.update_status(
            session, task.id, TaskStatusUpdate(status=TaskStatus.COMPLETED)
        )
        await session.commit()
        return

    try:
        pdf_bytes = _download_pdf(document.source_url, timeout, max_retries)
        key = f"documents/{document.id}/original.pdf"
        uri = storage.store(key, pdf_bytes)
        await document_repo.update(session, document.id, DocumentUpdate(gcs_uri=uri))
        parse_task = await task_repo.create(
            session,
            TaskCreate(
                document_id=document.id,
                step=PipelineStep.PARSE,
                status=TaskStatus.PENDING,
            ),
        )
        await session.commit()
        queue_publisher.publish(
            next_topic,
            QueueMessage(task_id=parse_task.id, document_id=document.id),
        )
        await task_repo.update_status(
            session, task.id, TaskStatusUpdate(status=TaskStatus.COMPLETED)
        )
        await session.commit()
        time.sleep(rate_limit_delay)
    except Exception as e:
        await session.rollback()
        logger.error(
            "Failed to download document %s from %s: %s",
            document.id,
            document.source_url,
            e,
        )
        await task_repo.update_status(
            session,
            task.id,
            TaskStatusUpdate(status=TaskStatus.FAILED, error_message=str(e)),
        )
        await session.commit()
