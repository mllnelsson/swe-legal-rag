import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Integer,
    Text,
    bindparam,
    func,
    select,
    update as sql_update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.session import (
    SessionCreate,
    SessionRead,
    SessionSummaryRow,
    SessionUpdate,
)
from shared.models.session import Session

# The two projections that let a conversation be listed without its transcript
# being read. `jsonb_extract_path_text` rather than the `history[0]["content"]`
# operator chain: it is one typed function call, so what comes back is `str`
# rather than an untyped JSON element the caller has to coerce.
_ENTRY_COUNT = func.jsonb_array_length(Session.history, type_=Integer)
_FIRST_MESSAGE = func.jsonb_extract_path_text(
    Session.history, "0", "content", type_=Text
)

# A session row is created before the agent runs, so a turn that failed, was
# aborted, or never started leaves one behind with nothing in it. Those are not
# conversations and must not reach a conversation list.
_HAS_HISTORY = _ENTRY_COUNT > 0


async def create(session: AsyncSession, dto: SessionCreate) -> SessionRead:
    chat_session = Session(history=dto.history)
    session.add(chat_session)
    await session.flush()
    await session.refresh(chat_session)
    return SessionRead.model_validate(chat_session)


async def get_by_id(session: AsyncSession, session_id: uuid.UUID) -> SessionRead | None:
    chat_session = await session.get(Session, session_id)
    return SessionRead.model_validate(chat_session) if chat_session else None


async def list_summaries(
    session: AsyncSession, *, limit: int, offset: int
) -> list[SessionSummaryRow]:
    """The conversations, most recently active first, without their transcripts.

    The projection is done by Postgres — `history -> 0 ->> 'content'` for the
    opening question and `jsonb_array_length` for the size — so the JSONB column
    itself is never sent over the wire to build a list. Sessions with no history
    are conversations that never happened; see `_HAS_HISTORY`.
    """
    statement = (
        select(
            Session.id,
            Session.created_at,
            Session.last_active_at,
            _FIRST_MESSAGE.label("first_message"),
            _ENTRY_COUNT.label("entry_count"),
        )
        .where(_HAS_HISTORY)
        .order_by(Session.last_active_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return [
        SessionSummaryRow.model_validate(row, from_attributes=True) for row in result
    ]


async def count_with_history(session: AsyncSession) -> int:
    """How many conversations exist — the `total` a page is a slice of."""
    result = await session.execute(
        select(func.count()).select_from(Session).where(_HAS_HISTORY)
    )
    return result.scalar_one()


async def delete(session: AsyncSession, session_id: uuid.UUID) -> bool:
    """Remove a conversation, reporting whether there was one.

    Nothing else references a session, and the traces its turns produced are
    keyed by `interaction_id` in file storage — they outlive the row.
    """
    chat_session = await session.get(Session, session_id)
    if chat_session is None:
        return False
    await session.delete(chat_session)
    await session.flush()
    return True


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
