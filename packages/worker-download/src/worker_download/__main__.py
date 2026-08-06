import logging

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.queue import create_queue_publisher
from shared.queue.base import QueueMessage, QueueSubscriber
from shared.repositories import document, task
from shared.storage import create_storage_backend
from shared.worker import serve, subscribe_step
from worker_download.config import get_download_settings
from worker_download.service import process_download

logger = logging.getLogger(__name__)

NAME = "worker-download"


def subscribe() -> QueueSubscriber:
    load_dotenv()
    settings = get_settings()
    download_settings = get_download_settings()

    storage = create_storage_backend(settings.storage)
    publisher = create_queue_publisher(settings.queue)

    async def handle(message: QueueMessage, session: AsyncSession) -> None:
        await process_download(
            message,
            session=session,
            document_repo=document,
            task_repo=task,
            storage=storage,
            queue_publisher=publisher,
            timeout=download_settings.download_request_timeout,
            max_retries=download_settings.download_max_retries,
            rate_limit_delay=download_settings.download_rate_limit_delay,
            next_topic=download_settings.download_next_topic,
        )

    # No trace scope: this worker makes no LLM calls, so there is nothing to
    # attribute.
    return subscribe_step(
        topic=download_settings.download_topic,
        queue_settings=settings.queue,
        handle=handle,
    )


def main() -> None:
    configure_logging()
    serve(subscribe(), name=NAME)


if __name__ == "__main__":
    main()
