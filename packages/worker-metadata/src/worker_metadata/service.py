from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentUpdate
from shared.enums import PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueuePublisher
from shared.repositories import DocumentRepo, TaskRepo
from shared.segmentation import find_segmentation_gaps, split_document
from shared.source_headline import parse_source_headline
from worker_metadata.patterns import (
    MetadataResult,
    extract_decision_number,
    is_complete,
)

logger = logging.getLogger(__name__)

# decision_number is absent here on purpose: it is never worth an LLM call, and
# is_complete() ignores it for the same reason.
_METADATA_FIELDS = ("case_number", "decision_date", "decision_outcome", "category")

# What the LLM half of metadata extraction looks like. The rule-based pass runs
# first and this fills only what it left blank.
type LLMMetadataExtractor = Callable[[str], Awaitable[MetadataResult]]


async def no_llm_extractor(raw_text: str) -> MetadataResult:
    """An extractor that declines, for callers with no provider wired up.

    Public because `scripts/run_step.py` runs the metadata step without
    reaching a model; it used to import this from `worker_metadata.__main__`,
    which meant a script depending on another package's entry point.
    """
    logger.info("No LLM configured; returning empty metadata")
    return MetadataResult()


async def process_metadata(
    document_id: UUID,
    task_id: UUID,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    queue_publisher: QueuePublisher,
    rule_extractor: Callable[[str, str | None], MetadataResult],
    llm_extractor: LLMMetadataExtractor,
    session: AsyncSession,
    next_topic: PipelineStep = PipelineStep.EXTRACT,
) -> None:
    async def body() -> None:
        document = await document_repo.get_by_id(session, document_id)
        if document is None:
            raise StepInputError(f"Document {document_id} not found")
        if document.raw_text is None:
            raise StepInputError(f"Document {document_id} has no raw text")

        result = rule_extractor(document.raw_text, document.source_headline)
        _log_template_drift(document_id, document.raw_text, document.source_headline)

        if not is_complete(result):
            missing = [f for f in _METADATA_FIELDS if getattr(result, f) is None]
            logger.info(
                "Document %s: rule-based incomplete, LLM fallback for fields: %s",
                document_id,
                missing,
            )
            # Body only: an appended lower-instance decision has its own date,
            # outcome and diarienummer, and the LLM cannot tell them apart.
            body = split_document(document.raw_text).body
            try:
                llm_result = await llm_extractor(body)
                for field in missing:
                    llm_value = getattr(llm_result, field)
                    if llm_value is not None:
                        setattr(result, field, llm_value)
            except Exception as exc:
                logger.warning(
                    "LLM extraction failed for document %s: %s", document_id, exc
                )

        await document_repo.update(
            session,
            document.id,
            DocumentUpdate(
                case_number=result.case_number,
                decision_number=result.decision_number,
                decision_date=result.decision_date,
                decision_outcome=result.decision_outcome,
                category=result.category,
            ),
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


def _log_template_drift(
    document_id: UUID, raw_text: str, source_headline: str | None
) -> None:
    """Warn when a document does not look like the rest of the corpus.

    Logged here and nowhere else: metadata is the first step that segments, and
    extract and chunk segment the same text — three copies of the same warning is
    noise. Never raises and never changes the outcome; the steady state across the
    corpus is silence, which is what makes the signal worth having.
    """
    segments = split_document(raw_text)

    gaps = find_segmentation_gaps(segments)
    if gaps:
        logger.warning(
            "Document %s did not match the decision template (%s) — "
            "check shared.segmentation against the source PDF",
            document_id,
            ", ".join(gap.value for gap in gaps),
        )

    from_document = extract_decision_number(segments)
    from_headline = parse_source_headline(source_headline)
    if from_document is None and from_headline is None:
        logger.warning(
            "Document %s has no decision number in its trailer, body or headline",
            document_id,
        )
    elif (
        from_document is not None
        and from_headline is not None
        and from_document != from_headline.decision_number
    ):
        logger.warning(
            "Document %s: trailer says decision %s, listing says %s — using the trailer",
            document_id,
            from_document,
            from_headline.decision_number,
        )
