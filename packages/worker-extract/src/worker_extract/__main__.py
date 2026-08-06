from __future__ import annotations

import logging

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from ai import install_file_tracing, worker_trace_scope
from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.queue import create_queue_publisher
from shared.queue.base import QueueMessage, QueueSubscriber
from shared.repositories import (
    document,
    document_entity,
    document_reference,
    entity,
    task,
    unresolved_reference,
)
from shared.worker import serve, subscribe_step
from worker_extract.config import get_extract_settings
from worker_extract.extractors.factory import create_extraction_strategy
from worker_extract.services.extraction_service import process_extraction

logger = logging.getLogger(__name__)

NAME = "worker-extract"


def subscribe() -> QueueSubscriber:
    load_dotenv()
    settings = get_settings()
    extract_settings = get_extract_settings()

    install_file_tracing()
    strategy = create_extraction_strategy()

    publisher = create_queue_publisher(settings.queue)

    async def handle(message: QueueMessage, session: AsyncSession) -> None:
        await process_extraction(
            document_id=message.document_id,
            task_id=message.task_id,
            document_repo=document,
            task_repo=task,
            entity_repo=entity,
            doc_entity_repo=document_entity,
            ref_repo=document_reference,
            unresolved_repo=unresolved_reference,
            queue_publisher=publisher,
            session=session,
            strategy=strategy,
            next_topic=extract_settings.extract_next_topic,
        )

    return subscribe_step(
        topic=extract_settings.extract_topic,
        queue_settings=settings.queue,
        handle=handle,
        scope=worker_trace_scope(NAME),
    )


def main() -> None:
    configure_logging()
    serve(subscribe(), name=NAME)


if __name__ == "__main__":
    main()
