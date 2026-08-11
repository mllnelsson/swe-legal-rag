"""Forced grounding: the precondition that makes a mid-tier model trustworthy.

The system prompt asks the agent to look at a free-text column's values before
filtering on it. These tests cover what happens when it does not — because a
prompt is a request, and the whole design rests on this being a rule.
"""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agents.config import SqlAgentSettings
from agents.sql import _tools
from agents.sql._dtos import SqlRows
from agents.sql._tools import (
    TOOL_LIST_COLUMN_VALUES,
    TOOL_NOTE_ASSUMPTION,
    TOOL_RUN_SQL,
    build_sql_tools,
)

# The sandbox is stubbed in every test here, so the session is threaded through
# but never touched.
NO_SESSION = cast("AsyncSession", object())


@pytest.fixture
def executed() -> list[tuple[str, dict | None]]:
    return []


@pytest.fixture(autouse=True)
def stub_sandbox(monkeypatch: pytest.MonkeyPatch, executed: list) -> None:
    """Replace the sandbox so these tests are about policy, not Postgres.

    Whether the read-only transaction works is an integration concern; whether a
    query is *allowed to reach it* is this module's.
    """

    async def fake_execute_readonly(
        session, sql, *, max_rows, statement_timeout_ms, params=None
    ):
        executed.append((sql, params))
        return SqlRows(
            columns=["varde", "antal"],
            rows=[["Avvisning", 7]],
            row_count=1,
            truncated=False,
        )

    monkeypatch.setattr(_tools, "execute_readonly", fake_execute_readonly)


@pytest.fixture
def tools() -> tuple[dict, object]:
    _definitions, executors, state = build_sql_tools(NO_SESSION, SqlAgentSettings())
    return executors, state


async def test_filtering_a_free_text_column_is_refused_before_grounding(
    tools, executed
) -> None:
    executors, state = tools

    result = await executors[TOOL_RUN_SQL](
        sql="SELECT count(*) FROM documents WHERE category = 'Avvisning'"
    )

    assert "error" in result
    assert TOOL_LIST_COLUMN_VALUES in result["error"]
    assert "documents.category" in result["error"]
    assert executed == [], "the query must not reach the database"
    # Recorded as a failed attempt so the refusal is visible in the trail.
    assert state.attempts[-1].ok is False


async def test_the_query_succeeds_once_the_column_has_been_grounded(
    tools, executed
) -> None:
    """The recovery path — a refusal must be correctable within the same loop."""
    executors, state = tools

    await executors[TOOL_LIST_COLUMN_VALUES](table="documents", column="category")
    result = await executors[TOOL_RUN_SQL](
        sql="SELECT count(*) FROM documents WHERE category = 'Avvisning'"
    )

    assert "error" not in result
    assert result["row_count"] == 1
    assert state.attempts[-1].ok is True


async def test_grounding_one_column_does_not_ground_another(tools) -> None:
    executors, _state = tools

    await executors[TOOL_LIST_COLUMN_VALUES](table="documents", column="category")
    result = await executors[TOOL_RUN_SQL](
        sql="SELECT count(*) FROM documents WHERE decision_outcome ILIKE '%avslår%'"
    )

    assert "documents.decision_outcome" in result["error"]


async def test_the_agents_own_grounding_query_needs_no_grounding(tools) -> None:
    """Otherwise the loop deadlocks on its own first move."""
    executors, _state = tools

    result = await executors[TOOL_RUN_SQL](
        sql="SELECT category, count(*) FROM documents GROUP BY 1"
    )

    assert "error" not in result


async def test_a_rejected_query_never_reaches_the_database(tools, executed) -> None:
    executors, _state = tools

    result = await executors[TOOL_RUN_SQL](sql="SELECT id FROM sessions")

    assert "sessions" in result["error"]
    assert executed == []


async def test_list_column_values_binds_its_filter(tools, executed) -> None:
    """The one caller-supplied value in a statement this package builds itself."""
    executors, _state = tools

    await executors[TOOL_LIST_COLUMN_VALUES](
        table="entities", column="name", contains="utlämnande"
    )

    sql, params = executed[-1]
    assert ":pattern" in sql
    assert params["pattern"] == "%utlämnande%"


async def test_list_column_values_rejects_an_unknown_column(tools) -> None:
    executors, _state = tools

    result = await executors[TOOL_LIST_COLUMN_VALUES](
        table="documents", column="hemligt"
    )

    assert "error" in result


async def test_list_column_values_rejects_a_blocked_column(tools) -> None:
    executors, _state = tools

    result = await executors[TOOL_LIST_COLUMN_VALUES](
        table="documents", column="raw_text"
    )

    assert "error" in result


async def test_assumptions_are_collected(tools) -> None:
    executors, state = tools

    await executors[TOOL_NOTE_ASSUMPTION](
        assumption="tolkade ÖN 2026 som decision_date"
    )

    assert state.assumptions == ["tolkade ÖN 2026 som decision_date"]
