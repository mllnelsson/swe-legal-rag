from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ai.embedding import EmbeddingProvider
from api.config import RetrievalSettings
from api.services.query_planner import QueryPlan
from llm_core import LLMProvider, Message, Role, generate_structured
from shared.dtos.document import DocumentRead
from shared.dtos.search import ChunkSearchResult, DocumentFilter
from shared.repositories import chunk as chunk_repo
from shared.repositories import document as document_repo
from shared.repositories import search as search_repo
from shared.search.rrf import rrf_fuse

logger = logging.getLogger(__name__)

# e5 models require the "query: " prefix for queries;
# chunks are embedded with "passage: " by worker-embed.
E5_QUERY_PREFIX = "query: "

# Per-chunk snippet length shown to the reranker LLM; keeps the prompt bounded.
SNIPPET_CHARS = 400


class RetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_text: str
    chunk_index: int
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
        case_number=doc.case_number if doc else None,
        decision_date=doc.decision_date if doc else None,
        decision_outcome=doc.decision_outcome if doc else None,
        category=doc.category if doc else None,
        gcs_uri=doc.gcs_uri if doc else None,
        source_url=doc.source_url if doc else "",
    )


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
    try:
        result = await generate_structured(messages, _RerankResult, provider=provider)
        assert isinstance(result, _RerankResult)
        valid = [i for i in result.ranked_indices if 0 <= i < len(chunks)]
        missing = [i for i in range(len(chunks)) if i not in set(valid)]
        return [chunks[i] for i in valid + missing]
    except Exception:
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

    embeddings = await embedding_provider.embed([E5_QUERY_PREFIX + plan.semantic_query])
    query_embedding = embeddings[0]

    vector_results, text_results = await asyncio.gather(
        chunk_repo.vector_search(
            session,
            query_embedding,
            candidate_ids,
            limit=settings.retrieval_search_limit,
        ),
        chunk_repo.text_search(
            session,
            plan.semantic_query,
            candidate_ids,
            limit=settings.retrieval_search_limit,
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
    top_chunks = [chunk_map[cid] for cid in fused_ids if cid in chunk_map]

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
