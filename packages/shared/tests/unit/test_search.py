"""Row-to-DTO mapping for the search repositories.

Whether a filter reaches the SQL is not testable against a mock session — an
`assert_called_once()` on `session.execute` passes just as happily when the
`WHERE` clause was never built. Those filters are verified for real against
Postgres in `packages/shared/tests/integration/test_search_repo.py`. What is
worth asserting here is the part that runs after the query comes back.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared.dtos.search import ChunkSearchResult, DocumentFilter
from shared.repositories import chunk as chunk_repo
from shared.repositories import search as search_repo


def _make_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    return session


def _scalars_result(values: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value = values
    return result


def _rows_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _make_chunk_row(score: float) -> SimpleNamespace:
    chunk = SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_text="test chunk",
        chunk_index=0,
        section="body",
        appendix_label=None,
    )
    return SimpleNamespace(Chunk=chunk, score=score)


class TestSearchFindCandidates:
    async def test_scalars_are_returned_as_a_list_of_ids(self):
        session = _make_session()
        ids = [uuid.uuid4(), uuid.uuid4()]
        session.execute.return_value = _scalars_result(ids)

        result = await search_repo.find_candidate_documents(session, DocumentFilter())

        assert result == ids


class TestChunkSearch:
    async def test_vector_search_maps_rows_to_chunk_results(self):
        session = _make_session()
        session.execute.return_value = _rows_result([_make_chunk_row(score=0.1)])

        results = await chunk_repo.vector_search(
            session, embedding=[0.1, 0.2], document_ids=None
        )

        assert len(results) == 1
        assert isinstance(results[0], ChunkSearchResult)
        assert results[0].chunk_text == "test chunk"
        assert results[0].score == 0.1

    async def test_text_search_maps_rows_to_chunk_results(self):
        session = _make_session()
        session.execute.return_value = _rows_result([_make_chunk_row(score=0.75)])

        results = await chunk_repo.text_search(
            session, query="kyrklig förvaltning", document_ids=None
        )

        assert len(results) == 1
        assert isinstance(results[0], ChunkSearchResult)
        assert results[0].score == 0.75
