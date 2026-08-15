import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    history: list[Any] = []


class SessionUpdate(BaseModel):
    last_active_at: datetime | None = None
    history: list[Any] | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    last_active_at: datetime
    history: list[Any]


class SessionSummaryRow(BaseModel):
    """One row of the conversation list, as Postgres projects it.

    Deliberately not `SessionRead` with fewer fields: a conversation's history is
    every question and every full answer it holds, and drawing a sidebar is no
    reason to load fifty of them. `first_message` and `entry_count` are computed
    in SQL so the column never leaves the database.

    `first_message` is `None` only for a history whose first entry carries no
    `content` — an empty history is filtered out before this row exists.
    """

    id: uuid.UUID
    created_at: datetime
    last_active_at: datetime
    first_message: str | None
    entry_count: int


class SessionSummary(BaseModel):
    """A conversation as the list shows it: what was asked first, and how much."""

    id: uuid.UUID
    created_at: datetime
    last_active_at: datetime
    title: str
    turn_count: int


class SessionTurn(BaseModel):
    """One question and the answer it got.

    `interaction_id` is the same id the `X-Interaction-Id` header carried, so a
    turn read back out of a session is still a lookup into the trace stream. It
    is `None` for entries written before that field existed.
    """

    question: str
    answer: str
    interaction_id: str | None


class SessionTranscript(BaseModel):
    """A whole conversation, paired back into turns.

    Carries no evidence, because none is stored: the passages, extracts and
    query results a turn gathered are deliberately not persisted.
    """

    id: uuid.UUID
    created_at: datetime
    last_active_at: datetime
    turns: list[SessionTurn]
