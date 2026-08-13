from ai import interaction_scope
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

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
        return await search_documents(
            body,
            db,
            embedding_provider=request.app.state.embedding_provider,
            settings=settings,
            llm_provider=request.app.state.structured_llm_provider,
        )


@router.get("/api/filters")
async def filters_endpoint(
    db: AsyncSession = Depends(get_db),
) -> DocumentFacets:
    """What values the search filters will actually match."""
    return await get_filters(db)
