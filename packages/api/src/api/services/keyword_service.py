"""Browsing the nämnd's own `Sökord` classification, and the hop back.

Keywords are `entities` rows of type `keyword`, so this reuses the entity repos
rather than owning storage of its own. It exists as a service separate from
`concept_service` because the two answer different questions: concepts are what
extraction *inferred* a decision is about, keywords are what the nämnd *declared*
it is about. Pinning the type here is what keeps that distinction visible in the
API instead of leaving callers to remember a query parameter.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from api.pagination import Page
from shared.dtos.document_entity import EntityDocumentRef
from shared.dtos.entity import EntityWithCount
from shared.enums import EntityType
from shared.repositories import document_entity as document_entity_repo
from shared.repositories import entity as entity_repo

logger = logging.getLogger(__name__)


async def list_keywords(
    session: AsyncSession,
    *,
    name_query: str | None = None,
    limit: int,
    offset: int = 0,
) -> Page[EntityWithCount]:
    """The keyword vocabulary, most-used first, with document counts."""
    keywords = await entity_repo.list_entities(
        session,
        entity_type=EntityType.KEYWORD,
        name_query=name_query,
        limit=limit,
        offset=offset,
    )
    total = await entity_repo.count_entities(
        session, entity_type=EntityType.KEYWORD, name_query=name_query
    )
    logger.debug("keywords listed count=%d total=%d", len(keywords), total)
    return Page(items=keywords, total=total, limit=limit, offset=offset)


async def list_documents_for_keyword(
    session: AsyncSession,
    keyword_id: uuid.UUID,
    *,
    limit: int,
    offset: int = 0,
) -> Page[EntityDocumentRef] | None:
    """Decisions classified under this keyword. ``None`` when it is not one.

    An id naming an entity of some other type is rejected rather than served:
    every keyword is an entity, but this endpoint promises the reverse, and
    silently answering for a legal concept would make the two indistinguishable
    to a caller paging through ids.
    """
    keyword = await entity_repo.get_by_id(session, keyword_id)
    if keyword is None or keyword.type != EntityType.KEYWORD:
        return None

    documents = await document_entity_repo.list_documents_for_entity(
        session, keyword_id, limit=limit, offset=offset
    )
    total = await document_entity_repo.count_documents_for_entity(session, keyword_id)
    logger.debug(
        "keyword %s documents count=%d total=%d", keyword_id, len(documents), total
    )
    return Page(items=documents, total=total, limit=limit, offset=offset)
