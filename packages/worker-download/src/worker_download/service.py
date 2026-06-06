import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories.document import DocumentRepository
from shared.repositories.task import TaskRepository
from shared.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_USER_AGENT = "church-legal-db/1.0 (PDF downloader)"


def _download_pdf(url: str, timeout: int, max_retries: int) -> bytes:
    last_error: Exception = RuntimeError(f"No attempts made for {url}")
    headers = {"User-Agent": _USER_AGENT}
    with httpx.Client(timeout=timeout, headers=headers) as client:
        for attempt in range(max(1, max_retries)):
            try:
                response = client.get(url)
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise
                last_error = e
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
    raise last_error


class DownloadService:
    def __init__(
        self,
        session: AsyncSession,
        document_repo: DocumentRepository,
        task_repo: TaskRepository,
        storage: StorageBackend,
        queue_publisher: QueuePublisher,
        timeout: int = 60,
        max_retries: int = 3,
        rate_limit_delay: float = 0.5,
        next_topic: str = "parse",
    ) -> None:
        self._session = session
        self._document_repo = document_repo
        self._task_repo = task_repo
        self._storage = storage
        self._queue_publisher = queue_publisher
        self._timeout = timeout
        self._max_retries = max_retries
        self._rate_limit_delay = rate_limit_delay
        self._next_topic = next_topic

    async def handle_message(self, message: QueueMessage) -> None:
        task = await self._task_repo.get_by_id(message.task_id)
        if task is None or task.status == "completed":
            logger.info("Task %s already completed or not found, skipping", message.task_id)
            return

        await self._task_repo.update_status(task.id, TaskStatusUpdate(status="processing"))
        await self._session.commit()

        document = await self._document_repo.get_by_id(message.document_id)
        if document is None:
            await self._task_repo.update_status(
                task.id,
                TaskStatusUpdate(
                    status="failed",
                    error_message=f"Document {message.document_id} not found",
                ),
            )
            await self._session.commit()
            return

        if document.gcs_uri is not None:
            parse_task = await self._task_repo.create(
                TaskCreate(document_id=document.id, step="parse", status="pending")
            )
            await self._session.commit()
            self._queue_publisher.publish(
                self._next_topic,
                QueueMessage(task_id=parse_task.id, document_id=document.id),
            )
            await self._task_repo.update_status(task.id, TaskStatusUpdate(status="completed"))
            await self._session.commit()
            return

        try:
            pdf_bytes = _download_pdf(document.source_url, self._timeout, self._max_retries)
            key = f"documents/{document.id}/original.pdf"
            uri = self._storage.store(key, pdf_bytes)
            await self._document_repo.update(document.id, DocumentUpdate(gcs_uri=uri))
            parse_task = await self._task_repo.create(
                TaskCreate(document_id=document.id, step="parse", status="pending")
            )
            await self._session.commit()
            self._queue_publisher.publish(
                self._next_topic,
                QueueMessage(task_id=parse_task.id, document_id=document.id),
            )
            await self._task_repo.update_status(task.id, TaskStatusUpdate(status="completed"))
            await self._session.commit()
            time.sleep(self._rate_limit_delay)
        except Exception as e:
            await self._session.rollback()
            logger.error(
                "Failed to download document %s from %s: %s",
                document.id,
                document.source_url,
                e,
            )
            await self._task_repo.update_status(
                task.id,
                TaskStatusUpdate(status="failed", error_message=str(e)),
            )
            await self._session.commit()
