"""Reading a single decision and browsing the corpus by metadata alone.

The detail view is one call on purpose: legal concepts, regulation references and
cited/citing cases are what a reader traverses next, so they arrive together with
the decision rather than as four follow-up requests.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.pagination import Page
from shared.dtos.document import DocumentRead
from shared.dtos.document_entity import DocumentEntityDetail
from shared.dtos.document_reference import ReferenceEdge
from shared.dtos.search import DocumentFilter
from shared.enums import ChunkSection, EntityType
from shared.repositories import chunk as chunk_repo
from shared.repositories import document as document_repo
from shared.repositories import document_entity as document_entity_repo
from shared.repositories import document_reference as document_reference_repo
from shared.repositories import search as search_repo
from shared.repositories import unresolved_reference as unresolved_reference_repo
from shared.storage.base import StorageBackend
from shared.storage.keys import document_pdf_key

logger = logging.getLogger(__name__)


class DocumentSummary(BaseModel):
    """A decision's identity — enough to list it or link to it."""

    document_id: uuid.UUID
    case_number: str | None
    decision_number: str | None
    decision_date: date | None
    category: str | None
    decision_outcome: str | None
    headline: str | None
    summary: str | None
    source_url: str
    source_published_at: datetime | None
    has_pdf: bool


class DocumentSections(BaseModel):
    """What parts the source PDF was cut into.

    Appendix labels are listed so a reader knows an appealed decision is attached
    before asking for its text.
    """

    body_chunk_count: int
    appendix_chunk_count: int
    appendix_labels: list[str]


class UnresolvedCitation(BaseModel):
    """A citation to a decision the corpus does not hold — text, not a link."""

    target_case_number: str
    reference_context: str | None


class DocumentDetail(BaseModel):
    document: DocumentSummary
    sections: DocumentSections
    # The nämnd's own `Sökord` classification, kept apart from `concepts`: those
    # were inferred from the prose, these were declared by the decision.
    keywords: list[DocumentEntityDetail]
    concepts: list[DocumentEntityDetail]
    regulations: list[DocumentEntityDetail]
    roles: list[DocumentEntityDetail]
    parishes: list[DocumentEntityDetail]
    # Extraction writes `type` as free text, so a value outside EntityType is
    # surfaced rather than silently dropped.
    other_entities: list[DocumentEntityDetail]
    references_out: list[ReferenceEdge]
    references_in: list[ReferenceEdge]
    unresolved_references: list[UnresolvedCitation]


class DocumentChunk(BaseModel):
    """A chunk as a reader sees it.

    Projected from ``ChunkRead`` to drop the embedding vector and the
    context-enriched text, neither of which is meaningful outside retrieval.
    """

    chunk_id: uuid.UUID
    chunk_index: int
    text: str
    section: ChunkSection
    appendix_label: str | None


def _to_summary(document: DocumentRead) -> DocumentSummary:
    return DocumentSummary(
        document_id=document.id,
        case_number=document.case_number,
        decision_number=document.decision_number,
        decision_date=document.decision_date,
        category=document.category,
        decision_outcome=document.decision_outcome,
        headline=document.source_headline,
        summary=document.summary,
        source_url=document.source_url,
        source_published_at=document.source_published_at,
        # The download worker records the stored PDF's URI; asking storage would
        # cost a round trip to learn the same thing.
        has_pdf=document.gcs_uri is not None,
    )


def _bucket_entities(
    entities: list[DocumentEntityDetail],
) -> dict[str, list[DocumentEntityDetail]]:
    buckets: dict[str, list[DocumentEntityDetail]] = {
        EntityType.KEYWORD: [],
        EntityType.LEGAL_CONCEPT: [],
        EntityType.REGULATION: [],
        EntityType.ROLE: [],
        EntityType.PARISH: [],
        "other": [],
    }
    for entity in entities:
        match entity.type:
            case EntityType.KEYWORD:
                buckets[EntityType.KEYWORD].append(entity)
            case EntityType.LEGAL_CONCEPT:
                buckets[EntityType.LEGAL_CONCEPT].append(entity)
            case EntityType.REGULATION:
                buckets[EntityType.REGULATION].append(entity)
            case EntityType.ROLE:
                buckets[EntityType.ROLE].append(entity)
            case EntityType.PARISH:
                buckets[EntityType.PARISH].append(entity)
            case _:
                logger.warning(
                    "Entity %s has unknown type %r", entity.name, entity.type
                )
                buckets["other"].append(entity)
    return buckets


def _summarise_sections(chunks: list[DocumentChunk]) -> DocumentSections:
    body = [chunk for chunk in chunks if chunk.section == ChunkSection.BODY]
    appendix = [chunk for chunk in chunks if chunk.section == ChunkSection.APPENDIX]
    labels = list(
        dict.fromkeys(
            chunk.appendix_label for chunk in appendix if chunk.appendix_label
        )
    )
    return DocumentSections(
        body_chunk_count=len(body),
        appendix_chunk_count=len(appendix),
        appendix_labels=labels,
    )


async def _read_chunks(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentChunk]:
    chunks = await chunk_repo.get_by_document_id(session, document_id)
    return [
        DocumentChunk(
            chunk_id=chunk.id,
            chunk_index=chunk.chunk_index,
            text=chunk.chunk_text,
            section=chunk.section,
            appendix_label=chunk.appendix_label,
        )
        for chunk in chunks
    ]


async def list_documents(
    session: AsyncSession,
    document_filter: DocumentFilter,
    *,
    limit: int,
    offset: int = 0,
    newest_first: bool = True,
) -> Page[DocumentSummary]:
    """Browse by metadata, no query text involved."""
    documents = await search_repo.list_filtered_documents(
        session, document_filter, limit=limit, offset=offset, newest_first=newest_first
    )
    total = await search_repo.count_filtered_documents(session, document_filter)
    return Page(
        items=[_to_summary(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_document_detail(
    session: AsyncSession, document_id: uuid.UUID
) -> DocumentDetail | None:
    document = await document_repo.get_by_id(session, document_id)
    if document is None:
        return None

    entities = await document_entity_repo.list_entities_for_document(
        session, document_id
    )
    references = await document_reference_repo.list_references_for_document(
        session, document_id
    )
    unresolved = await unresolved_reference_repo.get_by_source_document_id(
        session, document_id
    )
    chunks = await _read_chunks(session, document_id)
    buckets = _bucket_entities(entities)

    return DocumentDetail(
        document=_to_summary(document),
        sections=_summarise_sections(chunks),
        keywords=buckets[EntityType.KEYWORD],
        concepts=buckets[EntityType.LEGAL_CONCEPT],
        regulations=buckets[EntityType.REGULATION],
        roles=buckets[EntityType.ROLE],
        parishes=buckets[EntityType.PARISH],
        other_entities=buckets["other"],
        references_out=references.outgoing,
        references_in=references.incoming,
        unresolved_references=[
            UnresolvedCitation(
                target_case_number=reference.target_case_number,
                reference_context=reference.reference_context,
            )
            for reference in unresolved
        ],
    )


async def get_document_chunks(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    section: ChunkSection | None = None,
) -> list[DocumentChunk] | None:
    """The decision's full text in order. ``None`` when the document is unknown."""
    document = await document_repo.get_by_id(session, document_id)
    if document is None:
        return None
    chunks = await _read_chunks(session, document_id)
    if section is None:
        return chunks
    return [chunk for chunk in chunks if chunk.section == section]


async def get_document_pdf(
    session: AsyncSession, document_id: uuid.UUID, storage: StorageBackend
) -> bytes | None:
    """The stored PDF's bytes, or ``None`` if there is no PDF to serve.

    Served through the API rather than as a backend URL: the local storage
    backend's ``get_url`` returns a filesystem path, which no browser can open.
    Proxying keeps one URL shape across local and GCS.
    """
    document = await document_repo.get_by_id(session, document_id)
    if document is None or document.gcs_uri is None:
        return None
    try:
        return storage.retrieve(document_pdf_key(document_id))
    except FileNotFoundError:
        # `gcs_uri` says the download worker stored it, so a miss here means
        # storage and database have diverged — worth a log, not a 500.
        logger.warning("Document %s has a stored URI but no PDF bytes", document_id)
        return None
