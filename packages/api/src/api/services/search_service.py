"""Deterministic hybrid search over the decision corpus.

No LLM sits in this path by default. The one unavoidable model call is the query
embedding; expansion is opt-in and, when used, only *adds* rankings to the same
fusion. Given the same inputs this returns the same results, which is what makes
it usable as a tool an agent can reason about.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

import ai
from ai.embedding import EmbeddingProvider
from api.config import SearchSettings
from api.pagination import Page, clamp_limit
from llm_core import LLMProvider
from shared.dtos.document import DocumentRead
from shared.dtos.search import ChunkSearchResult, DocumentFacets, DocumentFilter
from shared.enums import ChunkSection
from shared.repositories import chunk as chunk_repo
from shared.repositories import document as document_repo
from shared.repositories import search as search_repo
from shared.repositories.chunk import Sections
from shared.search import is_empty_filter, rrf_fuse_scored

logger = logging.getLogger(__name__)

# Upper bound on a single search query. Generous because the endpoint is a POST
# precisely so a long question does not have to be squeezed into a query string.
MAX_QUERY_CHARS = 2000


class SearchQuery(BaseModel):
    """Everything the search path needs, independent of how it arrived.

    Deliberately free of FastAPI types: the same model serves an HTTP route, an
    MCP tool call, or a direct call from a test.
    """

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    # Caller-supplied phrasings, fused alongside `query`. An agent that
    # reinterprets the user's question passes them here and keeps the search
    # deterministic; `expand` is the convenience for clients with no model.
    queries: list[str] | None = None
    expand: bool = False
    filter: DocumentFilter = DocumentFilter()
    limit: int | None = None
    offset: int = Field(default=0, ge=0)
    include_appendices: bool = False
    chunks_per_document: int | None = None


class SearchChunk(BaseModel):
    """A matched passage, verbatim, with how each arm ranked it."""

    chunk_id: uuid.UUID
    chunk_index: int
    text: str
    section: ChunkSection
    appendix_label: str | None
    score: float
    # None means that arm did not return this chunk at all. Together with
    # `score` they make the fused ordering auditable rather than opaque.
    vector_rank: int | None
    text_rank: int | None


class SearchHit(BaseModel):
    """One decision, with the passages that matched it."""

    document_id: uuid.UUID
    case_number: str | None
    decision_number: str | None
    decision_date: date | None
    category: str | None
    decision_outcome: str | None
    headline: str | None
    # Written by the ingestion pipeline, not generated per request.
    summary: str | None
    source_url: str
    score: float
    matched_chunk_count: int
    chunks: list[SearchChunk]


class SearchDiagnostics(BaseModel):
    """What the search actually did, so a caller can trust or debug the result."""

    filter_applied: bool
    # None when no filter was applied; 0 means the filter matched nothing, which
    # is why the result set is empty.
    candidate_document_count: int | None
    vector_hit_count: int
    text_hit_counts: dict[str, int]
    fused_chunk_count: int
    expanded: bool
    widened_to_appendices: bool


class SearchResponse(Page[SearchHit]):
    # Echoed so an expanded search can be replayed exactly: pass these back as
    # `queries` with `expand` off and the result is identical.
    effective_queries: list[str]
    diagnostics: SearchDiagnostics


class _ArmOutcome(BaseModel):
    rankings: list[list[uuid.UUID]]
    chunks: dict[uuid.UUID, ChunkSearchResult]
    vector_ranks: dict[uuid.UUID, int]
    text_ranks: dict[uuid.UUID, int]
    vector_hit_count: int
    text_hit_counts: dict[str, int]


def _dedupe_queries(question: str, extra: list[str], max_variants: int) -> list[str]:
    """The original question first, then distinct variants, capped."""
    queries = [question]
    seen = {question.strip().casefold()}
    for candidate in extra:
        normalised = candidate.strip()
        if not normalised or normalised.casefold() in seen:
            continue
        seen.add(normalised.casefold())
        queries.append(normalised)
        if len(queries) == max_variants + 1:
            break
    return queries


async def _expansion_variants(
    question: str, *, max_variants: int, provider: LLMProvider | None
) -> list[str]:
    try:
        result = await ai.expand_query(
            question, max_variants=max_variants, provider=provider
        )
        return result.variants
    except Exception:
        # Swallowed on purpose, mirroring the reranker: losing expansion costs
        # recall, not results. The trace records the failure.
        logger.warning("Query expansion failed; searching the original query alone")
        return []


async def _resolve_queries(
    query: SearchQuery, settings: SearchSettings, provider: LLMProvider | None
) -> tuple[list[str], bool]:
    """The phrasings to search, and whether an LLM produced any of them."""
    max_variants = settings.search_max_query_variants
    if query.queries:
        # Explicit variants win outright: a caller that supplied its own has
        # already decided how to reinterpret the question.
        return _dedupe_queries(query.query, query.queries, max_variants), False
    if not query.expand:
        return [query.query], False
    variants = await _expansion_variants(
        query.query, max_variants=max_variants, provider=provider
    )
    return _dedupe_queries(query.query, variants, max_variants), bool(variants)


async def _embed_queries(
    queries: list[str], *, embedding_provider: EmbeddingProvider, expand_vector: bool
) -> list[list[float]]:
    # The query side of the embedding model's asymmetric prefix pair, read from
    # `llm_config.yaml` so it cannot drift from the passage side worker-embed uses.
    query_prefix, _ = ai.get_embedding_prefixes()
    to_embed = queries if expand_vector else queries[:1]
    return await embedding_provider.embed([query_prefix + q for q in to_embed])


async def _run_arms(
    session: AsyncSession,
    *,
    queries: list[str],
    query_embeddings: list[list[float]],
    candidate_ids: list[uuid.UUID] | None,
    sections: Sections,
    arm_limit: int,
) -> _ArmOutcome:
    """Every arm of the hybrid search, in parallel, as rankings to fuse."""
    vector_calls = [
        chunk_repo.vector_search(
            session, embedding, candidate_ids, limit=arm_limit, sections=sections
        )
        for embedding in query_embeddings
    ]
    text_calls = [
        chunk_repo.text_search(
            session, query, candidate_ids, limit=arm_limit, sections=sections
        )
        for query in queries
    ]
    results = await asyncio.gather(*vector_calls, *text_calls)
    vector_results = list(results[: len(vector_calls)])
    text_results = list(results[len(vector_calls) :])

    rankings: list[list[uuid.UUID]] = []
    chunks: dict[uuid.UUID, ChunkSearchResult] = {}
    vector_ranks: dict[uuid.UUID, int] = {}
    text_ranks: dict[uuid.UUID, int] = {}

    for hits in vector_results:
        rankings.append([hit.id for hit in hits])
        for rank, hit in enumerate(hits, start=1):
            chunks.setdefault(hit.id, hit)
            # Best rank across variants: the reported rank is the strongest
            # showing, not whichever arm happened to run last.
            vector_ranks[hit.id] = min(vector_ranks.get(hit.id, rank), rank)

    text_hit_counts: dict[str, int] = {}
    for query, hits in zip(queries, text_results, strict=True):
        rankings.append([hit.id for hit in hits])
        text_hit_counts[query] = len(hits)
        for rank, hit in enumerate(hits, start=1):
            chunks.setdefault(hit.id, hit)
            text_ranks[hit.id] = min(text_ranks.get(hit.id, rank), rank)

    return _ArmOutcome(
        rankings=rankings,
        chunks=chunks,
        vector_ranks=vector_ranks,
        text_ranks=text_ranks,
        vector_hit_count=len({hit.id for hits in vector_results for hit in hits}),
        text_hit_counts=text_hit_counts,
    )


def _make_search_chunk(
    chunk: ChunkSearchResult, score: float, outcome: _ArmOutcome
) -> SearchChunk:
    return SearchChunk(
        chunk_id=chunk.id,
        chunk_index=chunk.chunk_index,
        text=chunk.chunk_text,
        section=chunk.section,
        appendix_label=chunk.appendix_label,
        score=score,
        vector_rank=outcome.vector_ranks.get(chunk.id),
        text_rank=outcome.text_ranks.get(chunk.id),
    )


def _group_by_document(
    fused: list[tuple[uuid.UUID, float]], outcome: _ArmOutcome
) -> dict[uuid.UUID, list[SearchChunk]]:
    """Fused chunks bucketed per document, each bucket in descending score order.

    `fused` arrives sorted, so a document's first chunk is also its best and
    insertion order already reflects document ranking.
    """
    grouped: dict[uuid.UUID, list[SearchChunk]] = {}
    for chunk_id, score in fused:
        chunk = outcome.chunks[chunk_id]
        grouped.setdefault(chunk.document_id, []).append(
            _make_search_chunk(chunk, score, outcome)
        )
    return grouped


def _rank_documents(
    grouped: dict[uuid.UUID, list[SearchChunk]],
) -> list[uuid.UUID]:
    """Best passage wins; more matching passages breaks ties.

    `document_id` is the final tiebreak rather than `decision_date`, so ordering
    is total without fetching metadata for documents that will not be returned.
    """
    return sorted(
        grouped,
        key=lambda document_id: (
            -grouped[document_id][0].score,
            -len(grouped[document_id]),
            str(document_id),
        ),
    )


def _make_hit(
    document: DocumentRead, chunks: list[SearchChunk], chunks_per_document: int
) -> SearchHit:
    return SearchHit(
        document_id=document.id,
        case_number=document.case_number,
        decision_number=document.decision_number,
        decision_date=document.decision_date,
        category=document.category,
        decision_outcome=document.decision_outcome,
        headline=document.source_headline,
        summary=document.summary,
        source_url=document.source_url,
        score=chunks[0].score,
        matched_chunk_count=len(chunks),
        chunks=chunks[:chunks_per_document],
    )


def _empty_response(
    query: SearchQuery,
    *,
    queries: list[str],
    limit: int,
    expanded: bool,
    filter_applied: bool,
    candidate_document_count: int | None,
) -> SearchResponse:
    return SearchResponse(
        items=[],
        total=0,
        limit=limit,
        offset=query.offset,
        effective_queries=queries,
        diagnostics=SearchDiagnostics(
            filter_applied=filter_applied,
            candidate_document_count=candidate_document_count,
            vector_hit_count=0,
            text_hit_counts={},
            fused_chunk_count=0,
            expanded=expanded,
            widened_to_appendices=False,
        ),
    )


async def search_documents(
    query: SearchQuery,
    session: AsyncSession,
    *,
    embedding_provider: EmbeddingProvider,
    settings: SearchSettings,
    llm_provider: LLMProvider | None = None,
) -> SearchResponse:
    limit = clamp_limit(
        query.limit,
        default=settings.search_default_limit,
        maximum=settings.search_max_limit,
    )
    chunks_per_document = clamp_limit(
        query.chunks_per_document,
        default=settings.search_chunks_per_document,
        maximum=settings.search_arm_limit,
    )

    # The candidate lookup comes first because it is cheap SQL and can end the
    # request outright — no point paying for an expansion or an embedding to
    # search a set already known to be empty.
    filter_applied = not is_empty_filter(query.filter)
    candidate_ids: list[uuid.UUID] | None = None
    candidate_count: int | None = None
    if filter_applied:
        candidate_ids = await search_repo.find_candidate_documents(
            session, query.filter, limit=settings.search_candidate_limit
        )
        candidate_count = len(candidate_ids)
        if not candidate_ids:
            # No widening. Chat prefers a wider net to no answer; a search tool
            # asked for "nothing older than 2024" must not answer with 2019.
            return _empty_response(
                query,
                queries=[query.query],
                limit=limit,
                expanded=False,
                filter_applied=True,
                candidate_document_count=0,
            )

    queries, expanded = await _resolve_queries(query, settings, llm_provider)
    query_embeddings = await _embed_queries(
        queries,
        embedding_provider=embedding_provider,
        expand_vector=settings.search_expand_vector_arm,
    )

    # Appendices hold the appealed decision — the lower instance's words, which
    # the nämnd may have overturned — so they stay out unless asked for.
    sections: Sections = None if query.include_appendices else [ChunkSection.BODY]
    outcome = await _run_arms(
        session,
        queries=queries,
        query_embeddings=query_embeddings,
        candidate_ids=candidate_ids,
        sections=sections,
        arm_limit=settings.search_arm_limit,
    )

    widened = False
    if not outcome.chunks and sections is not None:
        # Nothing in the nämnd's own text matched. Widen once rather than return
        # empty; every chunk carries its section, so the caller can still tell
        # whose words these are.
        logger.info("No body chunks matched; widening search to appendices")
        outcome = await _run_arms(
            session,
            queries=queries,
            query_embeddings=query_embeddings,
            candidate_ids=candidate_ids,
            sections=None,
            arm_limit=settings.search_arm_limit,
        )
        widened = True

    fused = rrf_fuse_scored(outcome.rankings)
    grouped = _group_by_document(fused, outcome)
    ranked_document_ids = _rank_documents(grouped)
    page_ids = ranked_document_ids[query.offset : query.offset + limit]

    # Metadata is fetched for the page only; ranking never needed it.
    documents = await asyncio.gather(
        *[document_repo.get_by_id(session, document_id) for document_id in page_ids]
    )

    items = [
        _make_hit(document, grouped[document.id], chunks_per_document)
        for document in documents
        if document is not None
    ]

    return SearchResponse(
        items=items,
        total=len(ranked_document_ids),
        limit=limit,
        offset=query.offset,
        effective_queries=queries,
        diagnostics=SearchDiagnostics(
            filter_applied=filter_applied,
            candidate_document_count=candidate_count,
            vector_hit_count=outcome.vector_hit_count,
            text_hit_counts=outcome.text_hit_counts,
            fused_chunk_count=len(fused),
            expanded=expanded,
            widened_to_appendices=widened,
        ),
    )


async def get_filters(session: AsyncSession) -> DocumentFacets:
    """The vocabulary the metadata filters accept."""
    return await search_repo.get_facets(session)
