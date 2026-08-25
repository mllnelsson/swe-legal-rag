from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api.pagination import Page
from shared.dtos.session import (
    SessionCreate,
    SessionRead,
    SessionSummary,
    SessionSummaryRow,
    SessionTranscript,
    SessionTurn,
)
from shared.repositories import session as session_repo

logger = logging.getLogger(__name__)

# DEPRECATED — chat-surface service, slated to move out of the api package with
# POST /api/chat and /api/sessions. See /api/chat-endpoint.md. Conversation state
# is the agent's concern; the retrieval endpoints are stateless.

# One conversation turn is a user question plus the assistant answer.
ENTRIES_PER_TURN = 2

# How much of the opening question names a conversation in a list. Long enough
# to tell two questions apart, short enough for a rail.
TITLE_MAX_CHARS = 60

# A conversation whose first entry holds no text. Only reachable through a
# hand-written history — `append_turn` never writes one.
UNTITLED = "Utan fråga"


async def get_or_create_session(
    session_id: uuid.UUID | None,
    session: AsyncSession,
) -> SessionRead:
    if session_id is not None:
        existing = await session_repo.get_by_id(session, session_id)
        if existing is not None:
            logger.debug(
                "session %s resumed with %d entries",
                session_id,
                len(existing.history),
            )
            return existing
        # Not an error: an unrecognised id silently starts a fresh conversation,
        # so this is the only place that fact is visible.
        logger.debug("session %s unknown, starting a fresh one", session_id)
    created = await session_repo.create(session, SessionCreate())
    logger.debug("session %s created", created.id)
    return created


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
    logger.debug(
        "turn appended session=%s question_chars=%d answer_chars=%d",
        session_id,
        len(question),
        len(answer),
    )


def session_title(first_message: str | None) -> str:
    """Name a conversation by what was asked first, in the asker's own words.

    No model is involved, deliberately. A generated title would put text in the
    navigation that the reader cannot check against anything, for a per-
    conversation cost, to replace a sentence they wrote themselves.
    """
    collapsed = " ".join((first_message or "").split())
    if collapsed == "":
        return UNTITLED
    if len(collapsed) <= TITLE_MAX_CHARS:
        return collapsed

    cut = collapsed[:TITLE_MAX_CHARS]
    # Break on the last whole word so the title never ends mid-word; a single
    # word longer than the budget has none, and is cut where it is.
    spaced = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return f"{spaced.rstrip()}…"


def _summary(row: SessionSummaryRow) -> SessionSummary:
    return SessionSummary(
        id=row.id,
        created_at=row.created_at,
        last_active_at=row.last_active_at,
        title=session_title(row.first_message),
        # Rounded up, so a history with an unpaired trailing entry still counts
        # as the turn it was part of rather than disappearing.
        turn_count=(row.entry_count + ENTRIES_PER_TURN - 1) // ENTRIES_PER_TURN,
    )


def transcript_turns(history: list[dict]) -> list[SessionTurn]:
    """Fold a stored history back into the turns it was appended as.

    `history` is untyped JSONB and the pairing is a convention `append_turn`
    upholds, not something Postgres enforces — so this is total rather than
    strict. A `user` entry opens a turn and the next `assistant` entry closes
    it; anything that does not fit still renders as *something*, because a
    history written by an older version of this code is a display problem and
    not a reason to fail a request.
    """
    turns: list[SessionTurn] = []
    awaiting_answer = False

    for entry in history:
        # Same default as `_entry_for_llm`: a roleless entry is a question.
        asked = entry.get("role", "user") == "user"
        content = _text(entry.get("content"))

        if not asked and awaiting_answer:
            turns[-1].answer = content
            awaiting_answer = False
            continue

        turns.append(
            SessionTurn(
                question=content if asked else "",
                answer="" if asked else content,
                interaction_id=_text_or_none(entry.get("interaction_id")),
            )
        )
        awaiting_answer = asked

    return turns


def _text(value: object) -> str:
    """Whatever is in an untyped JSONB field, as something renderable."""
    return value if isinstance(value, str) else ""


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


async def list_sessions(
    session: AsyncSession, *, limit: int, offset: int
) -> Page[SessionSummary]:
    """Every conversation this app holds, most recently active first.

    Every one of them: there are no accounts, so there is no owner to filter by
    — which the interface says out loud rather than leaving to be discovered.
    """
    rows = await session_repo.list_summaries(session, limit=limit, offset=offset)
    total = await session_repo.count_with_history(session)
    return Page(
        items=[_summary(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_transcript(
    session_id: uuid.UUID, session: AsyncSession
) -> SessionTranscript | None:
    """One conversation, read back as turns. `None` when there is no such row.

    What comes back is what was said and nothing else. The passages, document
    extracts and query rows a turn was built on are not stored — see
    `append_turn` — so a reopened conversation carries no citations, and the
    interface has to say so instead of showing an empty source list.
    """
    stored = await session_repo.get_by_id(session, session_id)
    if stored is None:
        return None
    return SessionTranscript(
        id=stored.id,
        created_at=stored.created_at,
        last_active_at=stored.last_active_at,
        turns=transcript_turns(stored.history),
    )


async def delete_session(session_id: uuid.UUID, session: AsyncSession) -> bool:
    """Forget a conversation. False when there was nothing to forget."""
    return await session_repo.delete(session, session_id)


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
    logger.debug("history window %d of %d entries", len(recent), len(history))
    return [_entry_for_llm(entry) for entry in recent]


def _entry_for_llm(entry: dict) -> dict:
    return {"role": entry.get("role", "user"), "content": entry.get("content", "")}
