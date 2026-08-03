import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.enums import PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from shared.storage.base import StorageBackend
from shared.storage.keys import document_pdf_key
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
# Content type the decision endpoint must answer with once redirects are followed.
PDF_CONTENT_TYPE = "application/pdf"


def _verified_pdf(response: httpx.Response, url: str) -> bytes:
    """Reject non-PDF payloads instead of storing them as if they were decisions.

    A CMS that answers an unknown id with an HTML error page still returns 200, so status
    alone is not evidence that a PDF came back.
    """
    content_type = (
        response.headers.get("content-type", "").split(";")[0].strip().lower()
    )
    if content_type and content_type != PDF_CONTENT_TYPE:
        raise DownloadError(
            f"Expected {PDF_CONTENT_TYPE} from {url}, got {content_type}"
        )
    return response.content


def _download_pdf(url: str, timeout: int, max_retries: int) -> bytes:
    last_error: Exception = DownloadError(f"No attempts made for {url}")
    headers = {"User-Agent": _USER_AGENT}
    # follow_redirects is required: crawl stores the canonical default.aspx?id=... URL,
    # which 302-redirects to the real /filer/....pdf path. httpx defaults this to False,
    # and raise_for_status() treats an unfollowed redirect as an error -- so every
    # download would fail with a 302 HTTPStatusError, which is below HTTP_SERVER_ERROR
    # and therefore re-raised without a retry.
    with httpx.Client(
        timeout=timeout, headers=headers, follow_redirects=True
    ) as client:
        for attempt in range(max(MIN_ATTEMPTS, max_retries)):
            try:
                response = client.get(url)
                response.raise_for_status()
                return _verified_pdf(response, url)
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
    async def body() -> None:
        document = await document_repo.get_by_id(session, message.document_id)
        if document is None:
            raise StepInputError(f"Document {message.document_id} not found")

        # Already downloaded (idempotent re-run): skip the fetch and let the
        # envelope publish the parse task + mark this one completed.
        if document.gcs_uri is not None:
            return

        pdf_bytes = _download_pdf(document.source_url, timeout, max_retries)
        uri = storage.store(document_pdf_key(document.id), pdf_bytes)
        await document_repo.update(session, document.id, DocumentUpdate(gcs_uri=uri))
        time.sleep(rate_limit_delay)

    await run_pipeline_step(
        task_repo=task_repo,
        session=session,
        task_id=message.task_id,
        document_id=message.document_id,
        next_step=next_topic,
        queue_publisher=queue_publisher,
        body=body,
    )
