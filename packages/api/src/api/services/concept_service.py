"""Browsing legal concepts, regulations, roles and parishes, and the hop back.

These are the graph's nodes. `list_documents_for_concept` is the traversal step:
from a concept named on one decision to every other decision that names it.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from api.pagination import Page
from shared.dtos.document_entity import EntityDocumentRef
from shared.dtos.entity import EntityWithCount
from shared.repositories import document_entity as document_entity_repo
from shared.repositories import entity as entity_repo

logger = logging.getLogger(__name__)


async def list_concepts(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    name_query: str | None = None,
    limit: int,
    offset: int = 0,
) -> Page[EntityWithCount]:
    entities = await entity_repo.list_entities(
        session,
        entity_type=entity_type,
        name_query=name_query,
        limit=limit,
        offset=offset,
    )
    total = await entity_repo.count_entities(
        session, entity_type=entity_type, name_query=name_query
    )
    logger.debug(
        "concepts listed count=%d total=%d type=%s",
        len(entities),
        total,
        entity_type or "all",
    )
    return Page(items=entities, total=total, limit=limit, offset=offset)


async def list_documents_for_concept(
    session: AsyncSession,
    entity_id: uuid.UUID,
    *,
    relevance: str | None = None,
    limit: int,
    offset: int = 0,
) -> Page[EntityDocumentRef] | None:
    """Decisions carrying this entity. ``None`` when the entity is unknown.

    Distinguishing "no such concept" from "a concept with no decisions" is what
    lets the caller answer a 404 rather than an empty page.
    """
    entity = await entity_repo.get_by_id(session, entity_id)
    if entity is None:
        return None

    documents = await document_entity_repo.list_documents_for_entity(
        session, entity_id, relevance=relevance, limit=limit, offset=offset
    )
    total = await document_entity_repo.count_documents_for_entity(
        session, entity_id, relevance=relevance
    )
    logger.debug(
        "concept %s documents count=%d total=%d", entity_id, len(documents), total
    )
    return Page(items=documents, total=total, limit=limit, offset=offset)
