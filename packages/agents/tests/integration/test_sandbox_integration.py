"""What only a real Postgres can prove: the read-only transaction holds.

The static guard in `_guard` narrows what the model can express; this is the
control that makes a write impossible regardless of what slipped past it.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agents.sql._sandbox import execute_readonly
from shared.dtos.document import DocumentCreate, DocumentUpdate

TIMEOUT_MS = 5000


async def _document_count(session: AsyncSession) -> int:
    result = await session.execute(text("SELECT count(*) FROM documents"))
    return result.scalar_one()


async def _add_document(session: AsyncSession, document_repo, url: str, **fields):
    created = await document_repo.create(session, DocumentCreate(source_url=url))
    if fields:
        await document_repo.update(session, created.id, DocumentUpdate(**fields))
    await session.commit()
    return created


async def test_select_returns_typed_rows(session: AsyncSession, document_repo) -> None:
    await _add_document(
        session,
        document_repo,
        "https://example.test/1",
        case_number="2026-0001",
        decision_date=datetime.date(2026, 1, 15),
    )

    rows = await execute_readonly(
        session,
        "SELECT case_number, decision_date FROM documents",
        max_rows=10,
        statement_timeout_ms=TIMEOUT_MS,
    )

    assert rows.columns == ["case_number", "decision_date"]
    # Dates leave as strings so the same rows serialise identically over HTTP and
    # back into the tool loop as a JSON tool result.
    assert rows.rows == [["2026-0001", "2026-01-15"]]
    assert rows.truncated is False


async def test_a_write_is_refused_by_postgres(session: AsyncSession) -> None:
    """Not by the guard — this bypasses it deliberately.

    The guard would reject an INSERT long before it got here; the point is that
    the transaction refuses it even when nothing else does.
    """
    with pytest.raises(Exception, match="read-only transaction"):
        await execute_readonly(
            session,
            "INSERT INTO documents (id, source_url) "
            f"VALUES ('{uuid.uuid4()}', 'https://example.test/written')",
            max_rows=10,
            statement_timeout_ms=TIMEOUT_MS,
        )

    assert await _document_count(session) == 0


async def test_the_session_is_usable_after_a_failed_statement(
    session: AsyncSession,
) -> None:
    """A poisoned transaction would break the request that follows."""
    with pytest.raises(Exception):
        await execute_readonly(
            session,
            "SELECT nonexistent_column FROM documents",
            max_rows=10,
            statement_timeout_ms=TIMEOUT_MS,
        )

    assert await _document_count(session) == 0


async def test_row_cap_flags_truncation(session: AsyncSession, document_repo) -> None:
    for index in range(5):
        await document_repo.create(
            session, DocumentCreate(source_url=f"https://example.test/{index}")
        )
    await session.commit()

    rows = await execute_readonly(
        session,
        "SELECT source_url FROM documents",
        max_rows=3,
        statement_timeout_ms=TIMEOUT_MS,
    )

    assert rows.row_count == 3
    assert rows.truncated is True


async def test_bound_parameters_are_not_interpolated(
    session: AsyncSession, document_repo
) -> None:
    await _add_document(
        session, document_repo, "https://example.test/1", category="Avvisning"
    )

    rows = await execute_readonly(
        session,
        "SELECT category FROM documents WHERE category ILIKE :pattern",
        max_rows=10,
        statement_timeout_ms=TIMEOUT_MS,
        params={"pattern": "%avvis%"},
    )

    assert rows.rows == [["Avvisning"]]
