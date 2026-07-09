from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from _fsstore import now, store_of
from shared.dtos.entity import EntityCreate, EntityRead


def _rows(session: AsyncSession) -> list[EntityRead]:
    return store_of(session).rows["entities"]


async def upsert(session: AsyncSession, dto: EntityCreate) -> EntityRead:
    rows = _rows(session)
    existing = next(
        (e for e in rows if e.name == dto.name and e.type == dto.type), None
    )
    if existing is not None:
        return existing
    entity = EntityRead(id=uuid4(), name=dto.name, type=dto.type, created_at=now())
    rows.append(entity)
    return entity
