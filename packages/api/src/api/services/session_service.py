from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.session import SessionCreate, SessionRead, SessionUpdate
from shared.repositories import session as session_repo

# DEPRECATED — chat-surface service, slated to move out of the api package with
# POST /api/chat. See /api/chat-endpoint.md. Conversation state is the agent's
# concern; the retrieval endpoints are stateless.

# One conversation turn is a user question plus the assistant answer.
ENTRIES_PER_TURN = 2


async def get_or_create_session(
    session_id: uuid.UUID | None,
    session: AsyncSession,
) -> SessionRead:
    if session_id is not None:
        existing = await session_repo.get_by_id(session, session_id)
        if existing is not None:
            return existing
    return await session_repo.create(session, SessionCreate())


async def append_turn(
    session_id: uuid.UUID,
    question: str,
    answer: str,
    session: AsyncSession,
) -> None:
    existing = await session_repo.get_by_id(session, session_id)
    if existing is None:
        return
    new_entries = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    await session_repo.update(
        session,
        session_id,
        SessionUpdate(
            history=list(existing.history) + new_entries,
            last_active_at=datetime.now(timezone.utc),
        ),
    )


def history_for_llm(session: SessionRead, max_turns: int) -> list[dict]:
    history = session.history
    max_entries = max_turns * ENTRIES_PER_TURN
    return list(history[-max_entries:]) if len(history) > max_entries else list(history)
