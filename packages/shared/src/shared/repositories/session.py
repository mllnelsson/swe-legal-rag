import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.session import SessionCreate, SessionRead, SessionUpdate
from shared.models.session import Session


async def create(session: AsyncSession, dto: SessionCreate) -> SessionRead:
    chat_session = Session(history=dto.history)
    session.add(chat_session)
    await session.flush()
    await session.refresh(chat_session)
    return SessionRead.model_validate(chat_session)


async def get_by_id(session: AsyncSession, session_id: uuid.UUID) -> SessionRead | None:
    chat_session = await session.get(Session, session_id)
    return SessionRead.model_validate(chat_session) if chat_session else None


async def update(
    session: AsyncSession, session_id: uuid.UUID, dto: SessionUpdate
) -> SessionRead | None:
    chat_session = await session.get(Session, session_id)
    if chat_session is None:
        return None
    for field, value in dto.model_dump(exclude_none=True).items():
        setattr(chat_session, field, value)
    await session.flush()
    await session.refresh(chat_session)
    return SessionRead.model_validate(chat_session)
