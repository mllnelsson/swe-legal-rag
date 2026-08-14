from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.session import SessionCreate, SessionRead
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
    *,
    interaction_id: str,
) -> None:
    """Record one turn, tagged with the interaction that produced it.

    `interaction_id` is what turns "which turn was this?" into a lookup in the
    [trace stream](/observability.md) rather than a guess from timestamps. It is
    stored, never sent to a model — see `history_for_llm`.

    The append is done by Postgres, not read-modify-written here, so two turns
    arriving at once both survive. A missing session is a no-op.
    """
    await session_repo.append_history(
        session,
        session_id,
        [
            {"role": "user", "content": question, "interaction_id": interaction_id},
            {"role": "assistant", "content": answer, "interaction_id": interaction_id},
        ],
        datetime.now(timezone.utc),
    )


def history_for_llm(session: SessionRead, max_turns: int) -> list[dict]:
    """The recent turns, projected to what a prompt should actually contain.

    The projection is load-bearing, not tidiness: `ai.synthesize_answer` renders
    the history with `json.dumps` over whole entries, so any bookkeeping field
    stored on a turn would otherwise be fed to the model as noise — and paid for
    on every subsequent turn.
    """
    history = session.history
    max_entries = max_turns * ENTRIES_PER_TURN
    recent = history[-max_entries:] if len(history) > max_entries else history
    return [_entry_for_llm(entry) for entry in recent]


def _entry_for_llm(entry: dict) -> dict:
    return {"role": entry.get("role", "user"), "content": entry.get("content", "")}
