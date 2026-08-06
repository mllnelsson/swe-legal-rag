from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai.dtos import ExtractedEntity
from shared.enums import EntityRelevance, EntityType, PipelineStep
from shared.pipeline import StepInputError, run_pipeline_step
from shared.queue.base import QueuePublisher
from shared.repositories import (
    DocumentEntityRepo,
    DocumentReferenceRepo,
    DocumentRepo,
    EntityRepo,
    TaskRepo,
    UnresolvedReferenceRepo,
)
from shared.segmentation import parse_keywords, split_document
from worker_extract.extractors.base import ExtractionStrategy
from worker_extract.services.entity_service import persist_entities
from worker_extract.services.reference_service import (
    process_references,
    reconcile_references,
)

logger = logging.getLogger(__name__)


def _own_identifiers(*identifiers: str | None) -> list[str]:
    """The identifiers by which this document refers to itself.

    A decision carries both an ärendenummer and a beslutsnummer; a citation in
    either space that matches one of them is a self-reference, not a cross-reference.
    """
    return [identifier for identifier in identifiers if identifier]


def _declared_keywords(trailer: str | None) -> list[ExtractedEntity]:
    """The trailer's ``Sökord:`` values as entities.

    Always PRIMARY: a keyword is the nämnd's own statement of what the case is
    about, never an incidental mention.
    """
    return [
        ExtractedEntity(
            name=keyword,
            type=EntityType.KEYWORD,
            relevance=EntityRelevance.PRIMARY,
        )
        for keyword in parse_keywords(trailer)
    ]


async def process_extraction(
    document_id: UUID,
    task_id: UUID,
    document_repo: DocumentRepo,
    task_repo: TaskRepo,
    entity_repo: EntityRepo,
    doc_entity_repo: DocumentEntityRepo,
    ref_repo: DocumentReferenceRepo,
    unresolved_repo: UnresolvedReferenceRepo,
    queue_publisher: QueuePublisher,
    session: AsyncSession,
    strategy: ExtractionStrategy,
    next_topic: PipelineStep = PipelineStep.CHUNK,
) -> None:
    """Extract entities, keywords and references from one document.

    Keywords are read straight off the trailer rather than through `strategy`.
    They are declared by the nämnd, not inferred, so every strategy mode must
    yield the same ones.

    `strategy` is injected rather than looked up here: two of the three modes
    construct an LLM provider, and building one per document is what a
    factory call inside the step body used to do. Every other worker builds its
    provider once at startup and passes it in.
    """

    async def body() -> None:
        document = await document_repo.get_by_id(session, document_id)
        if document is None:
            raise StepInputError(f"Document {document_id} not found")
        if document.raw_text is None:
            raise StepInputError(f"Document {document_id} has no raw text")

        segments = split_document(document.raw_text)
        result = await strategy(segments, document.case_number)

        # The trailer is the only source of a keyword, so a strategy that emits
        # one has invented a declared field. `parsing.py` builds its valid-type
        # set from `EntityType`, which would otherwise let such a response
        # through.
        inferred = [
            entity for entity in result.entities if entity.type != EntityType.KEYWORD
        ]
        declared = _declared_keywords(segments.trailer)
        await persist_entities(
            session,
            entity_repo,
            doc_entity_repo,
            document_id,
            inferred + declared,
        )
        await process_references(
            session,
            document_repo,
            ref_repo,
            unresolved_repo,
            document_id,
            _own_identifiers(document.case_number, document.decision_number),
            result.references,
        )
        reconciled = await reconcile_references(
            session,
            unresolved_repo,
            ref_repo,
            document_id,
            _own_identifiers(document.case_number, document.decision_number),
        )
        logger.info(
            "Extracted for document %s: %d inferred entities, %d declared keywords, "
            "%d references cited, %d earlier reference(s) resolved to it",
            document_id,
            len(inferred),
            len(declared),
            len(result.references),
            reconciled,
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
