from __future__ import annotations

import datetime
import logging

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from ai import install_file_tracing, worker_trace_scope
from ai.providers.roles import LLMRole, create_llm_provider
from ai.services import extract_metadata as _ai_extract_metadata
from llm_core import LLMProvider
from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.queue import create_queue_publisher
from shared.queue.base import QueueMessage, QueueSubscriber
from shared.repositories import document, task
from shared.worker import serve, subscribe_step
from worker_metadata.config import get_metadata_settings
from worker_metadata.patterns import MetadataResult, extract_metadata_rule_based
from worker_metadata.service import LLMMetadataExtractor, process_metadata

logger = logging.getLogger(__name__)

NAME = "worker-metadata"


def _make_llm_extractor(provider: LLMProvider) -> LLMMetadataExtractor:
    async def extract(raw_text: str) -> MetadataResult:
        ai_result = await _ai_extract_metadata(raw_text, provider=provider)
        return MetadataResult(
            case_number=ai_result.case_number,
            decision_date=_parse_decision_date(ai_result.decision_date),
            decision_outcome=ai_result.decision_outcome,
            category=ai_result.category,
        )

    return extract


def _parse_decision_date(raw: str | None) -> datetime.date | None:
    """The model returns a date as free text, so it may not be one.

    A malformed date leaves the field unset rather than failing the document —
    the rule-based pass may already have found it, and one bad field is not
    worth discarding the other three. Logged because a model that has started
    returning a new format is worth noticing.
    """
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        logger.warning("LLM returned an unparseable decision_date: %r", raw)
        return None


def subscribe() -> QueueSubscriber:
    load_dotenv()
    settings = get_settings()
    metadata_settings = get_metadata_settings()

    install_file_tracing()
    llm_extractor = _make_llm_extractor(create_llm_provider(LLMRole.STRUCTURED))

    publisher = create_queue_publisher(settings.queue)

    async def handle(message: QueueMessage, session: AsyncSession) -> None:
        await process_metadata(
            document_id=message.document_id,
            task_id=message.task_id,
            document_repo=document,
            task_repo=task,
            queue_publisher=publisher,
            rule_extractor=extract_metadata_rule_based,
            llm_extractor=llm_extractor,
            session=session,
            next_topic=metadata_settings.metadata_next_topic,
        )

    return subscribe_step(
        topic=metadata_settings.metadata_topic,
        queue_settings=settings.queue,
        handle=handle,
        scope=worker_trace_scope(NAME),
    )


def main() -> None:
    configure_logging()
    serve(subscribe(), name=NAME)


if __name__ == "__main__":
    main()
