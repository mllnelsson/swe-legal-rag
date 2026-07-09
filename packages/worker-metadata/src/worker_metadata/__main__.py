from __future__ import annotations

import asyncio
import datetime
import logging
import signal

from dotenv import load_dotenv

from ai.services import extract_metadata as _ai_extract_metadata
from shared.config import get_settings
from shared.db import get_async_session
from shared.queue import create_queue_publisher, create_queue_subscriber
from shared.queue.base import QueueMessage
from shared.repositories import document, task
from worker_metadata.config import get_metadata_settings
from worker_metadata.patterns import MetadataResult, extract_metadata_rule_based
from worker_metadata.service import process_metadata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _llm_extractor(raw_text: str, missing_fields: list[str]) -> MetadataResult:
    ai_result = await _ai_extract_metadata(raw_text)
    decision_date: datetime.date | None = None
    if ai_result.decision_date:
        try:
            decision_date = datetime.date.fromisoformat(ai_result.decision_date)
        except ValueError:
            pass
    return MetadataResult(
        case_number=ai_result.case_number,
        decision_date=decision_date,
        decision_outcome=ai_result.decision_outcome,
        category=ai_result.category,
    )


def main() -> None:
    load_dotenv()
    settings = get_settings()
    metadata_settings = get_metadata_settings()

    publisher = create_queue_publisher(settings.queue)
    subscriber = create_queue_subscriber(settings.queue)

    def handle_message(message: QueueMessage) -> None:
        async def _handle() -> None:
            async with get_async_session() as session:
                await process_metadata(
                    document_id=message.document_id,
                    task_id=message.task_id,
                    document_repo=document,
                    task_repo=task,
                    queue_publisher=publisher,
                    rule_extractor=extract_metadata_rule_based,
                    llm_extractor=_llm_extractor,
                    session=session,
                    next_topic=metadata_settings.metadata_next_topic,
                )

        asyncio.run(_handle())

    subscriber.subscribe(metadata_settings.metadata_topic, handle_message)

    def shutdown_handler(_signum: int, _frame: object) -> None:
        logger.info("Shutdown signal received, stopping...")
        subscriber.shutdown()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info(
        "Metadata worker starting, subscribing to topic: %s",
        metadata_settings.metadata_topic,
    )
    subscriber.start()


if __name__ == "__main__":
    main()
