import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.entity import EntityCreate, EntityRead, EntityWithCount
from shared.models.document_entity import DocumentEntity
from shared.models.entity import Entity


async def upsert(session: AsyncSession, dto: EntityCreate) -> EntityRead:
    result = await session.execute(
        select(Entity).where(Entity.name == dto.name, Entity.type == dto.type)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        entity = Entity(name=dto.name, type=dto.type)
        session.add(entity)
        await session.flush()
        await session.refresh(entity)
    return EntityRead.model_validate(entity)


async def get_by_id(session: AsyncSession, entity_id: uuid.UUID) -> EntityRead | None:
    entity = await session.get(Entity, entity_id)
    return EntityRead.model_validate(entity) if entity else None


async def get_by_name_and_type(
    session: AsyncSession, name: str, entity_type: str
) -> EntityRead | None:
    result = await session.execute(
        select(Entity).where(Entity.name == name, Entity.type == entity_type)
    )
    entity = result.scalar_one_or_none()
    return EntityRead.model_validate(entity) if entity else None


async def list_by_type(session: AsyncSession, entity_type: str) -> list[EntityRead]:
    result = await session.execute(select(Entity).where(Entity.type == entity_type))
    return [EntityRead.model_validate(row) for row in result.scalars()]


def _apply_entity_filter(stmt, entity_type: str | None, name_query: str | None):
    if entity_type is not None:
        stmt = stmt.where(Entity.type == entity_type)
    if name_query is not None:
        stmt = stmt.where(Entity.name.ilike(f"%{name_query}%"))
    return stmt


async def list_entities(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    name_query: str | None = None,
    limit: int,
    offset: int = 0,
) -> list[EntityWithCount]:
    """Browse entities, most-cited first.

    An inner join drops entities with no documents: they cannot be traversed to
    anything, so listing them would only offer dead ends.
    """
    document_count = func.count(DocumentEntity.document_id)
    stmt = (
        select(Entity.id, Entity.name, Entity.type, document_count)
        .select_from(Entity)
        .join(DocumentEntity, DocumentEntity.entity_id == Entity.id)
        .group_by(Entity.id, Entity.name, Entity.type)
    )
    stmt = _apply_entity_filter(stmt, entity_type, name_query)
    stmt = stmt.order_by(document_count.desc(), Entity.name).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [
        EntityWithCount(
            id=entity_id, name=name, type=entity_type_value, document_count=count
        )
        for entity_id, name, entity_type_value, count in result.all()
    ]


async def count_entities(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    name_query: str | None = None,
) -> int:
    stmt = (
        select(func.count(func.distinct(Entity.id)))
        .select_from(Entity)
        .join(DocumentEntity, DocumentEntity.entity_id == Entity.id)
    )
    stmt = _apply_entity_filter(stmt, entity_type, name_query)
    result = await session.execute(stmt)
    return result.scalar_one()
