import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, update as sql_update
from sqlalchemy.dialects.postgresql import JSONB
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


async def append_history(
    session: AsyncSession,
    session_id: uuid.UUID,
    entries: list[dict[str, Any]],
    last_active_at: datetime,
) -> None:
    """Append entries to a session's history without reading it first.

    Postgres does the append, in one statement, so two turns arriving at once
    both survive. Reading the array into Python and writing it back — which is
    what this replaces — loses whichever turn commits first.

    Deliberately not a `SELECT ... FOR UPDATE`: the append runs after the chat
    stream has finished, inside the request-scoped session, so a row lock taken
    here would be held for the whole turn. `||` takes none.

    A missing session is a no-op, because the UPDATE simply matches no row.
    """
    statement = (
        sql_update(Session)
        .where(Session.id == session_id)
        .values(
            history=Session.history.op("||")(
                bindparam("new_entries", value=entries, type_=JSONB)
            ),
            last_active_at=last_active_at,
        )
    )
    await session.execute(statement)


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
