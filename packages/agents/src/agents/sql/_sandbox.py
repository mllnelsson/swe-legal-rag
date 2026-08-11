"""Executing model-authored SQL without letting it change anything.

The control that makes this safe is Postgres', not Python's: every statement runs
inside a transaction explicitly marked `READ ONLY`, which the server enforces
against writes the static guard in `_guard` might not recognise. The transaction
is always rolled back, so the session is handed back exactly as it arrived.
"""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agents.sql._dtos import SqlRows, SqlValue

__all__ = ["execute_readonly"]


def _to_json_primitive(value: Any) -> SqlValue:
    """Narrow a driver value to something a JSON response can carry.

    Dates and UUIDs become strings rather than being left to the response
    encoder, so the same rows serialise identically whether they leave over HTTP
    or go back into the tool loop as a JSON tool result.
    """
    match value:
        case None | bool() | int() | float() | str():
            return value
        case decimal.Decimal():
            return float(value)
        case uuid.UUID() | datetime.date() | datetime.datetime() | datetime.time():
            return str(value)
        case _:
            return str(value)


async def execute_readonly(
    session: AsyncSession,
    sql: str,
    *,
    max_rows: int,
    statement_timeout_ms: int,
    params: dict[str, Any] | None = None,
) -> SqlRows:
    """Run `sql` in a read-only transaction and return at most `max_rows` rows.

    `params` binds values for the statements this package builds itself; SQL the
    model wrote carries its own literals and passes none.

    `session` is left with no open transaction on return, whether or not the
    statement succeeded.
    """
    # `SET TRANSACTION READ ONLY` only applies to a transaction that has not yet
    # done any work, so the session must be at a clean point before it runs.
    await session.rollback()
    try:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await session.execute(
            text(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
        )
        result = await session.execute(text(sql), params or {})
        # One row past the cap: the extra row is what distinguishes "exactly
        # max_rows matched" from "more matched and we stopped looking".
        fetched = result.fetchmany(max_rows + 1)
        columns = list(result.keys())
    finally:
        await session.rollback()

    truncated = len(fetched) > max_rows
    rows = [[_to_json_primitive(value) for value in row] for row in fetched[:max_rows]]
    return SqlRows(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
    )
