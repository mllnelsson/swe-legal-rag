from __future__ import annotations

import uuid
from datetime import datetime, timezone

from shared.dtos.session import SessionCreate, SessionRead, SessionUpdate
from shared.repositories.session import SessionRepository


async def get_or_create_session(
    session_id: uuid.UUID | None,
    repo: SessionRepository,
) -> SessionRead:
    if session_id is not None:
        existing = await repo.get_by_id(session_id)
        if existing is not None:
            return existing
    return await repo.create(SessionCreate())


async def append_turn(
    session_id: uuid.UUID,
    question: str,
    answer: str,
    repo: SessionRepository,
) -> None:
    existing = await repo.get_by_id(session_id)
    if existing is None:
        return
    new_entries = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    await repo.update(
        session_id,
        SessionUpdate(
            history=list(existing.history) + new_entries,
            last_active_at=datetime.now(timezone.utc),
        ),
    )


def history_for_llm(session: SessionRead, max_turns: int) -> list[dict]:
    history = session.history
    max_entries = max_turns * 2
    return list(history[-max_entries:]) if len(history) > max_entries else list(history)
