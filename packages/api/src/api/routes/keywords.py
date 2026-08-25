import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.access_log import note, preview
from api.config import SearchSettings, get_search_settings
from api.dependencies import get_db
from api.pagination import Page, clamp_limit
from api.services.keyword_service import list_documents_for_keyword, list_keywords
from shared.dtos.document_entity import EntityDocumentRef
from shared.dtos.entity import EntityWithCount

router = APIRouter()


@router.get("/api/keywords")
async def list_keywords_endpoint(
    request: Request,
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    settings: SearchSettings = Depends(get_search_settings),
) -> Page[EntityWithCount]:
    """Browse the nämnd's own `Sökord` classification, most-used first.

    Unlike `/api/concepts`, these values were declared by the decisions
    themselves rather than inferred from their prose.
    """
    page = await list_keywords(
        db,
        name_query=q,
        limit=clamp_limit(
            limit,
            default=settings.search_default_limit,
            maximum=settings.search_max_limit,
        ),
        offset=offset,
    )
    note(
        request,
        count=len(page.items),
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        q=preview(q) if q else "-",
    )
    return page


@router.get("/api/keywords/{keyword_id}/documents")
async def keyword_documents_endpoint(
    keyword_id: uuid.UUID,
    request: Request,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    settings: SearchSettings = Depends(get_search_settings),
) -> Page[EntityDocumentRef]:
    """Every decision classified under this keyword — one hop through the graph.

    No `relevance` parameter, unlike the concept traversal: a declared keyword is
    always primary, so there is nothing to narrow by.
    """
    page = await list_documents_for_keyword(
        db,
        keyword_id,
        limit=clamp_limit(
            limit,
            default=settings.search_default_limit,
            maximum=settings.search_max_limit,
        ),
        offset=offset,
    )
    note(
        request,
        keyword=keyword_id,
        count=len(page.items) if page else 0,
        total=page.total if page else 0,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return page
