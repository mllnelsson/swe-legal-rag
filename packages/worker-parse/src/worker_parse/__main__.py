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
from worker_parse.config import get_parse_settings
from worker_parse.parser import parse_pdf_with_pypdfium2
from worker_parse.service import process_parse

logger = logging.getLogger(__name__)

NAME = "worker-parse"


def subscribe() -> QueueSubscriber:
    load_dotenv()
    settings = get_settings()
    parse_settings = get_parse_settings()

    storage = create_storage_backend(settings.storage)
    publisher = create_queue_publisher(settings.queue)

    async def handle(message: QueueMessage, session: AsyncSession) -> None:
        await process_parse(
            document_id=message.document_id,
            task_id=message.task_id,
            storage=storage,
            document_repo=document,
            task_repo=task,
            queue_publisher=publisher,
            parser=parse_pdf_with_pypdfium2,
            session=session,
            next_topic=parse_settings.parse_next_topic,
        )

    # No trace scope: this worker makes no LLM calls, so there is nothing to
    # attribute.
    return subscribe_step(
        topic=parse_settings.parse_topic,
        queue_settings=settings.queue,
        handle=handle,
    )


def main() -> None:
    configure_logging()
    serve(subscribe(), name=NAME)


if __name__ == "__main__":
    main()
