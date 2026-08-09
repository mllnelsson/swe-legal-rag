"""The wire contract of the SQL agent.

Deliberately free of FastAPI types, like `api.services.search_service.SearchQuery`:
the same models serve an HTTP route, a test, or a future MCP tool wrapper.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MAX_QUESTION_CHARS",
    "SqlAgentRequest",
    "SqlAgentResult",
    "SqlAttempt",
    "SqlRows",
    "SqlValue",
]

MAX_QUESTION_CHARS = 2000

# Every value is coerced to a JSON primitive by the sandbox, so a caller never
# has to know that `decision_date` arrived as a `datetime.date`.
type SqlValue = str | int | float | bool | None


class SqlRows(BaseModel):
    """A result set, already narrowed to what the caller may be handed."""

    model_config = ConfigDict(frozen=True)

    columns: list[str]
    rows: list[list[SqlValue]]
    row_count: int
    # True when the query matched more rows than the cap allowed back. An
    # aggregate that is truncated is not an answer, and the caller must be able
    # to tell that apart from a complete one.
    truncated: bool


class SqlAttempt(BaseModel):
    """One `run_sql` call the agent made, successful or not.

    Kept for every iteration, not just the last: the trail is what lets a reader
    see that the agent grounded its predicates before committing to a query.
    """

    model_config = ConfigDict(frozen=True)

    sql: str
    ok: bool
    error: str | None = None
    row_count: int | None = None


class SqlAgentRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class SqlAgentResult(BaseModel):
    """The query and its rows — never a natural-language answer.

    Reasoning about what the rows *mean* is the caller's job. This agent
    provides; interpreting is a separate responsibility, and merging the two
    would hide a wrong query behind fluent prose.
    """

    model_config = ConfigDict(frozen=True)

    answered: bool
    sql: str | None
    columns: list[str] = []
    rows: list[list[SqlValue]] = []
    row_count: int = 0
    truncated: bool = False
    # The model's closing message: a short note on what it ran, or — when
    # `answered` is False — why the question could not be answered from this
    # schema.
    note: str = ""
    # Every ambiguity the agent resolved on its own. With no user to ask, it
    # picks a reading and says so here rather than choosing silently.
    assumptions: list[str] = []
    attempts: list[SqlAttempt] = []
    iterations: int = 0
