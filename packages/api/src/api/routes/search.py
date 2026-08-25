from ai import interaction_scope
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.access_log import note, preview
from api.config import SearchSettings, get_search_settings
from api.dependencies import get_db
from api.services.search_service import (
    SearchQuery,
    SearchResponse,
    get_filters,
    search_documents,
)
from shared.dtos.search import DocumentFacets

router = APIRouter()

_SOURCE = "api.search"


@router.post("/api/search")
async def search_endpoint(
    body: SearchQuery,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: SearchSettings = Depends(get_search_settings),
) -> SearchResponse:
    """Hybrid search over the decision corpus.

    POST rather than GET: the query is free text of arbitrary length and the
    filter is a nested object with list-valued fields.
    """
    # This path is LLM-free unless expansion is asked for, but not call-free:
    # `ai.expand_query` and a remote embedding both land here. Without a scope
    # their records carry no correlation key at all and cannot be attributed to
    # the request that paid for them.
    with interaction_scope(source=_SOURCE):
        response = await search_documents(
            body,
            db,
            embedding_provider=request.app.state.embedding_provider,
            settings=settings,
            llm_provider=request.app.state.structured_llm_provider,
        )

    diagnostics = response.diagnostics
    note(
        request,
        q=preview(body.query),
        hits=len(response.items),
        total=response.total,
        queries=len(response.effective_queries),
        expanded=diagnostics.expanded,
        filtered=diagnostics.filter_applied,
        widened=diagnostics.widened_to_appendices,
        # The number a caller reads to tell a close match from a distant one; on
        # the exit line it is what says whether an empty result was a miss or a
        # floor rejection. See /retrieval/deterministic-search.md.
        top_sim=diagnostics.top_vector_similarity,
    )
    return response


@router.get("/api/filters")
async def filters_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DocumentFacets:
    """What values the search filters will actually match."""
    facets = await get_filters(db)
    note(
        request,
        categories=len(facets.categories),
        outcomes=len(facets.decision_outcomes),
        keywords=len(facets.keywords),
        entity_types=len(facets.entity_types),
        documents=facets.document_count,
    )
    return facets
