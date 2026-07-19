import asyncio
import logging
import signal

from dotenv import load_dotenv

from shared.config import get_settings
from shared.db import get_async_session
from shared.queue import create_queue_publisher, create_queue_subscriber
from shared.queue.base import QueueMessage
from shared.repositories import document, task
from shared.storage import create_storage_backend
from worker_download.config import get_download_settings
from worker_download.service import process_download

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    settings = get_settings()
    download_settings = get_download_settings()

    storage = create_storage_backend(settings.storage)
    publisher = create_queue_publisher(settings.queue)
    subscriber = create_queue_subscriber(settings.queue)

    def handle_message(message: QueueMessage) -> None:
        async def _handle() -> None:
            async with get_async_session() as session:
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

        asyncio.run(_handle())

    subscriber.subscribe(download_settings.download_topic, handle_message)

    def shutdown_handler(_signum: int, _frame: object) -> None:
        logger.info("Shutdown signal received, stopping...")
        subscriber.shutdown()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info(
        "Download worker starting, subscribing to topic: %s",
        download_settings.download_topic,
    )
    subscriber.start()


if __name__ == "__main__":
    main()
