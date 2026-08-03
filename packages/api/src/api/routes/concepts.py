import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import SearchSettings, get_search_settings
from api.dependencies import get_db
from api.pagination import Page, clamp_limit
from api.services.concept_service import list_concepts, list_documents_for_concept
from shared.dtos.document_entity import EntityDocumentRef
from shared.dtos.entity import EntityWithCount
from shared.enums import EntityRelevance, EntityType

router = APIRouter()


@router.get("/api/concepts")
async def list_concepts_endpoint(
    entity_type: EntityType | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    settings: SearchSettings = Depends(get_search_settings),
) -> Page[EntityWithCount]:
    """Browse the graph's nodes — legal concepts, regulations, roles, parishes."""
    return await list_concepts(
        db,
        entity_type=entity_type,
        name_query=q,
        limit=clamp_limit(
            limit,
            default=settings.search_default_limit,
            maximum=settings.search_max_limit,
        ),
        offset=offset,
    )


@router.get("/api/concepts/{entity_id}/documents")
async def concept_documents_endpoint(
    entity_id: uuid.UUID,
    relevance: EntityRelevance | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    settings: SearchSettings = Depends(get_search_settings),
) -> Page[EntityDocumentRef]:
    """Every decision carrying this entity — one hop through the graph."""
    page = await list_documents_for_concept(
        db,
        entity_id,
        relevance=relevance,
        limit=clamp_limit(
            limit,
            default=settings.search_default_limit,
            maximum=settings.search_max_limit,
        ),
        offset=offset,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    return page
