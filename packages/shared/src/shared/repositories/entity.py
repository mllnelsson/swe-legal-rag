import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.entity import EntityCreate, EntityRead
from shared.models.entity import Entity


class EntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, dto: EntityCreate) -> EntityRead:
        result = await self._session.execute(
            select(Entity).where(Entity.name == dto.name, Entity.type == dto.type)
        )
        entity = result.scalar_one_or_none()
        if entity is None:
            entity = Entity(name=dto.name, type=dto.type)
            self._session.add(entity)
            await self._session.flush()
            await self._session.refresh(entity)
        return EntityRead.model_validate(entity)

    async def get_by_id(self, entity_id: uuid.UUID) -> EntityRead | None:
        entity = await self._session.get(Entity, entity_id)
        return EntityRead.model_validate(entity) if entity else None

    async def get_by_name_and_type(self, name: str, entity_type: str) -> EntityRead | None:
        result = await self._session.execute(
            select(Entity).where(Entity.name == name, Entity.type == entity_type)
        )
        entity = result.scalar_one_or_none()
        return EntityRead.model_validate(entity) if entity else None

    async def list_by_type(self, entity_type: str) -> list[EntityRead]:
        result = await self._session.execute(select(Entity).where(Entity.type == entity_type))
        return [EntityRead.model_validate(row) for row in result.scalars()]
