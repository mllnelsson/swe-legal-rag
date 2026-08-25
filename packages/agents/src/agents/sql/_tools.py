"""The tools the SQL agent is given, and the state that constrains them.

The load-bearing idea is in `_run_sql`: a query that *filters* on one of the
free-text columns is refused until the agent has actually looked at that column's
values. The system prompt asks for the same thing, but a prompt is a request and
this is a precondition — the difference decides whether a mid-tier model can be
trusted with the job.

A refusal is not an error. It is returned to the model as a tool result, so the
next iteration corrects itself through the loop's ordinary repair path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from llm_core import ToolDefinition
from sqlalchemy.ext.asyncio import AsyncSession

from agents.config import SqlAgentSettings
from agents.errors import SqlRejectedError
from agents.sql._dtos import SqlAttempt, SqlRows
from agents.sql._guard import check_sql, find_predicate_columns
from agents.sql._sandbox import execute_readonly
from agents.sql._schema import blocked_columns, exposed_column_names
from agents.sql._semantic_model import SemanticModelDocument, resolve

logger = logging.getLogger(__name__)

__all__ = ["GroundingState", "build_sql_tools"]

TOOL_LIST_COLUMN_VALUES = "list_column_values"
TOOL_RUN_SQL = "run_sql"
TOOL_NOTE_ASSUMPTION = "note_assumption"


@dataclass
class GroundingState:
    """What the agent has done so far in one run.

    Mutable and single-run: `build_sql_tools` creates one per invocation and the
    executors close over it, so nothing leaks between requests.
    """

    grounded_columns: set[tuple[str, str]] = field(default_factory=set)
    assumptions: list[str] = field(default_factory=list)
    attempts: list[SqlAttempt] = field(default_factory=list)
    # The rows of the most recent successful `run_sql`. `attempts` records that a
    # query ran and how many rows it matched, but not the rows themselves — and
    # the answer needs them.
    last_rows: SqlRows | None = None


def _column_values_sql(table: str, column: str, *, contains: str | None) -> str:
    """A distinct-value tally for one column.

    `table` and `column` are interpolated, which is safe only because both have
    been checked against `exposed_column_names()` first. The caller-supplied
    `contains` is bound, never interpolated.
    """
    filter_clause = f" AND {column} ILIKE :pattern" if contains else ""
    return (
        f"SELECT {column} AS varde, count(*) AS antal "  # noqa: S608 — see docstring
        f"FROM {table} "
        f"WHERE {column} IS NOT NULL{filter_clause} "
        f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT :limit"
    )


async def _list_column_values(
    session: AsyncSession,
    state: GroundingState,
    settings: SqlAgentSettings,
    document: SemanticModelDocument,
    *,
    table: str,
    column: str,
    contains: str | None = None,
) -> dict[str, Any]:
    if column in blocked_columns(document):
        return {"error": f"Kolumnen {column} kan inte läsas."}
    if (table, column) not in exposed_column_names(document):
        return {"error": f"Det finns ingen kolumn {table}.{column}."}

    rows = await execute_readonly(
        session,
        _column_values_sql(table, column, contains=contains),
        max_rows=settings.sql_agent_max_column_values,
        statement_timeout_ms=settings.sql_agent_statement_timeout_ms,
        params={
            "limit": settings.sql_agent_max_column_values,
            **({"pattern": f"%{contains}%"} if contains else {}),
        },
    )

    # Recorded even when the filter narrowed the result: the agent has now seen
    # real values for this column, which is what the precondition is about.
    state.grounded_columns.add((table, column))
    return {
        "values": [{"varde": row[0], "antal": row[1]} for row in rows.rows],
        "truncated": rows.truncated,
    }


def _ungrounded_message(ungrounded: set[tuple[str, str]]) -> str:
    listed = ", ".join(f"{table}.{column}" for table, column in sorted(ungrounded))
    calls = " ".join(
        f"{TOOL_LIST_COLUMN_VALUES}(table='{table}', column='{column}')"
        for table, column in sorted(ungrounded)
    )
    return (
        f"Frågan villkorar på fritextkolumnen/kolumnerna {listed} utan att värdena "
        f"har lästs. Kör {calls} först och bygg sedan villkoret på de värden som "
        "faktiskt finns."
    )


async def _run_sql(
    session: AsyncSession,
    state: GroundingState,
    settings: SqlAgentSettings,
    document: SemanticModelDocument,
    *,
    sql: str,
) -> dict[str, Any]:
    try:
        check_sql(sql, document)
    except SqlRejectedError as exc:
        state.attempts.append(SqlAttempt(sql=sql, ok=False, error=str(exc)))
        return {"error": str(exc)}

    ungrounded = find_predicate_columns(sql, document) - state.grounded_columns
    if ungrounded:
        message = _ungrounded_message(ungrounded)
        state.attempts.append(SqlAttempt(sql=sql, ok=False, error=message))
        return {"error": message}

    try:
        rows = await execute_readonly(
            session,
            sql,
            max_rows=settings.sql_agent_max_rows,
            statement_timeout_ms=settings.sql_agent_statement_timeout_ms,
        )
    except Exception as exc:
        # Postgres' own message is the most useful repair hint there is, so it
        # goes back to the model verbatim rather than being flattened.
        logger.info("SQL agent query failed: %s", exc)
        state.attempts.append(SqlAttempt(sql=sql, ok=False, error=str(exc)))
        return {"error": str(exc)}

    state.attempts.append(SqlAttempt(sql=sql, ok=True, row_count=rows.row_count))
    state.last_rows = rows
    return {
        "columns": rows.columns,
        "rows": rows.rows,
        "row_count": rows.row_count,
        "truncated": rows.truncated,
    }


async def _note_assumption(state: GroundingState, *, assumption: str) -> dict[str, Any]:
    state.assumptions.append(assumption)
    return {"ok": True}


_TOOL_DEFINITIONS = [
    ToolDefinition(
        name=TOOL_LIST_COLUMN_VALUES,
        summary=(
            "visar vilka värden som faktiskt finns i en kolumn, med antal per värde"
        ),
        description=(
            "Visar vilka värden som faktiskt förekommer i en kolumn, med antal per "
            "värde. Använd detta innan du villkorar på en fritextkolumn — annars "
            "vägrar run_sql att köra frågan."
        ),
        parameters={
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Tabellnamn."},
                "column": {"type": "string", "description": "Kolumnnamn."},
                "contains": {
                    "type": "string",
                    "description": "Valfritt. Visa bara värden som innehåller texten.",
                },
            },
            "required": ["table", "column"],
        },
    ),
    ToolDefinition(
        name=TOOL_RUN_SQL,
        summary=("kör en läsande fråga och returnerar raderna"),
        description=(
            "Kör en läsande SQL-fråga mot korpusen och returnerar raderna. En sats "
            "åt gången, SELECT eller WITH. Den sista lyckade frågan är ditt svar."
        ),
        parameters={
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "PostgreSQL SELECT-sats."}
            },
            "required": ["sql"],
        },
    ),
    ToolDefinition(
        name=TOOL_NOTE_ASSUMPTION,
        summary=("registrerar ett tolkningsval du gjort"),
        description=(
            "Registrerar ett tolkningsval du gjort, t.ex. vilken kolumn ett årtal "
            "syftar på eller vilka värden en ämnesterm matchar. Anropa detta för "
            "varje term som kunde tolkas på mer än ett sätt."
        ),
        parameters={
            "type": "object",
            "properties": {
                "assumption": {
                    "type": "string",
                    "description": "Tolkningsvalet, i en mening på svenska.",
                }
            },
            "required": ["assumption"],
        },
    ),
]


def build_sql_tools(
    session: AsyncSession,
    settings: SqlAgentSettings,
    document: SemanticModelDocument | None = None,
) -> tuple[list[ToolDefinition], dict[str, Any], GroundingState]:
    """Tool definitions, their executors, and the state both share.

    The state is returned rather than hidden so the caller can read the
    assumptions and attempts back out once the loop has finished.

    The semantic model is resolved once here and closed over, so every tool call
    in a run enforces the same policy even if the file changes underneath.
    """
    state = GroundingState()
    model = resolve(document)

    async def list_column_values(
        table: str, column: str, contains: str | None = None
    ) -> dict[str, Any]:
        return await _list_column_values(
            session,
            state,
            settings,
            model,
            table=table,
            column=column,
            contains=contains,
        )

    async def run_sql(sql: str) -> dict[str, Any]:
        return await _run_sql(session, state, settings, model, sql=sql)

    async def note_assumption(assumption: str) -> dict[str, Any]:
        return await _note_assumption(state, assumption=assumption)

    executors = {
        TOOL_LIST_COLUMN_VALUES: list_column_values,
        TOOL_RUN_SQL: run_sql,
        TOOL_NOTE_ASSUMPTION: note_assumption,
    }
    return _TOOL_DEFINITIONS, executors, state
