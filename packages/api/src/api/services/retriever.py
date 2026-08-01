from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ai import get_embedding_prefixes
from ai.embedding import EmbeddingProvider
from api.config import RetrievalSettings
from api.services.query_planner import QueryPlan
from llm_core import LLMProvider, Message, Role, generate_structured, trace_context
from shared.dtos.document import DocumentRead
from shared.dtos.search import ChunkSearchResult, DocumentFilter
from shared.enums import ChunkSection
from shared.repositories import chunk as chunk_repo
from shared.repositories import document as document_repo
from shared.repositories import search as search_repo
from shared.repositories.chunk import Sections
from shared.search.rrf import rrf_fuse

logger = logging.getLogger(__name__)

# The query side of the embedding model's asymmetric prefix pair. Both sides
# come from `llm_config.yaml` so they cannot drift apart — worker-embed reads
# the passage half from the same place.

# Per-chunk snippet length shown to the reranker LLM; keeps the prompt bounded.
SNIPPET_CHARS = 400

_RERANK_SOURCE = "api.retriever.rerank"


class RetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_text: str
    chunk_index: int
    section: ChunkSection = ChunkSection.BODY
    appendix_label: str | None = None
    case_number: str | None = None
    decision_date: date | None = None
    decision_outcome: str | None = None
    category: str | None = None
    gcs_uri: str | None = None
    source_url: str = ""


def _filter_is_empty(f: DocumentFilter) -> bool:
    return (
        f.date_from is None
        and f.date_to is None
        and f.category is None
        and f.decision_outcome is None
        and not f.entity_names
        and not f.entity_types
        and f.references_case_number is None
    )


def _make_retrieved_chunk(
    chunk: ChunkSearchResult, doc: DocumentRead | None
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        chunk_text=chunk.chunk_text,
        chunk_index=chunk.chunk_index,
        section=chunk.section,
        appendix_label=chunk.appendix_label,
        case_number=doc.case_number if doc else None,
        decision_date=doc.decision_date if doc else None,
        decision_outcome=doc.decision_outcome if doc else None,
        category=doc.category if doc else None,
        gcs_uri=doc.gcs_uri if doc else None,
        source_url=doc.source_url if doc else "",
    )


def _sections_for(plan: QueryPlan, settings: RetrievalSettings) -> Sections:
    """Which parts of a document this query may draw from.

    ``None`` means every part. Body-only is the default because an appendix holds
    the appealed decision, and its embedding carries the body-derived summary — so
    similarity alone cannot keep the two instances apart.
    """
    if settings.retrieval_include_appendices or plan.include_appendices:
        return None
    return [ChunkSection.BODY]


async def _hybrid_search(
    session: AsyncSession,
    query_embedding: list[float],
    plan: QueryPlan,
    settings: RetrievalSettings,
    candidate_ids: list[uuid.UUID] | None,
    sections: Sections,
) -> list[ChunkSearchResult]:
    vector_results, text_results = await asyncio.gather(
        chunk_repo.vector_search(
            session,
            query_embedding,
            candidate_ids,
            limit=settings.retrieval_search_limit,
            sections=sections,
        ),
        chunk_repo.text_search(
            session,
            plan.semantic_query,
            candidate_ids,
            limit=settings.retrieval_search_limit,
            sections=sections,
        ),
    )

    fused_ids = rrf_fuse(
        [
            [r.id for r in vector_results],
            [r.id for r in text_results],
        ]
    )[: settings.retrieval_top_k]

    chunk_map: dict[uuid.UUID, ChunkSearchResult] = {r.id: r for r in vector_results}
    chunk_map.update({r.id: r for r in text_results})
    return [chunk_map[cid] for cid in fused_ids if cid in chunk_map]


class _RerankResult(BaseModel):
    ranked_indices: list[int]


async def _rerank(
    question: str,
    chunks: list[ChunkSearchResult],
    *,
    provider: LLMProvider | None = None,
) -> list[ChunkSearchResult]:
    snippets = "\n".join(
        f"[{i}] {chunk.chunk_text[:SNIPPET_CHARS]}" for i, chunk in enumerate(chunks)
    )
    messages = [
        Message(
            role=Role.user,
            content=(
                f"Question: {question}\n\n"
                "Rank these chunks from most to least relevant. "
                "Return 'ranked_indices' with all indices in relevance order:\n\n"
                f"{snippets}"
            ),
        )
    ]
    # This is the one caller that reaches past `ai` straight into llm-core, so
    # it has to name itself or its records would be the only unattributed ones.
    try:
        with trace_context(source=_RERANK_SOURCE):
            result = await generate_structured(
                messages, _RerankResult, provider=provider
            )
        valid = [i for i in result.ranked_indices if 0 <= i < len(chunks)]
        missing = [i for i in range(len(chunks)) if i not in set(valid)]
        return [chunks[i] for i in valid + missing]
    except Exception:
        # Swallowed on purpose: a failed rerank costs relevance, not an answer.
        # The trace records the failure, which is where it becomes visible.
        logger.warning("Rerank failed; keeping RRF order")
        return chunks


async def retrieve(
    plan: QueryPlan,
    session: AsyncSession,
    *,
    embedding_provider: EmbeddingProvider,
    settings: RetrievalSettings,
    llm_provider: LLMProvider | None = None,
) -> list[RetrievedChunk]:
    candidate_ids: list[uuid.UUID] | None
    if _filter_is_empty(plan.filter):
        candidate_ids = None
    else:
        candidates = await search_repo.find_candidate_documents(session, plan.filter)
        if not candidates:
            logger.warning(
                "Filter yielded no candidates; falling back to unfiltered search"
            )
            candidate_ids = None
        else:
            candidate_ids = candidates

    query_prefix, _ = get_embedding_prefixes()
    embeddings = await embedding_provider.embed([query_prefix + plan.semantic_query])
    query_embedding = embeddings[0]

    sections = _sections_for(plan, settings)
    top_chunks = await _hybrid_search(
        session, query_embedding, plan, settings, candidate_ids, sections
    )
    if not top_chunks and sections is not None:
        # Nothing in the nämnd's own text answers this. Rather than return empty,
        # widen to the appealed decisions — the caller still sees which section
        # each excerpt came from and can say so.
        logger.info("No body chunks matched; widening search to appendices")
        top_chunks = await _hybrid_search(
            session, query_embedding, plan, settings, candidate_ids, None
        )

    if settings.retrieval_rerank_enabled and top_chunks:
        top_chunks = await _rerank(
            plan.semantic_query, top_chunks, provider=llm_provider
        )

    doc_ids = list(dict.fromkeys(c.document_id for c in top_chunks))
    doc_reads = await asyncio.gather(
        *[document_repo.get_by_id(session, did) for did in doc_ids]
    )
    doc_map = {d.id: d for d in doc_reads if d is not None}

    return [
        _make_retrieved_chunk(chunk, doc_map.get(chunk.document_id))
        for chunk in top_chunks
        if chunk.document_id in doc_map
    ]
