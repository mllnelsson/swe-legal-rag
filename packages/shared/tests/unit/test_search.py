import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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


class TestSearchFindCandidates:
    @pytest.mark.asyncio
    async def test_empty_filter_returns_all_doc_ids(self):
        session = _make_session()
        doc_id = uuid.uuid4()
        session.execute.return_value = _scalars_result([doc_id])

        result = await search_repo.find_candidate_documents(session, DocumentFilter())

        session.execute.assert_called_once()
        assert result == [doc_id]

    @pytest.mark.asyncio
    async def test_date_from_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        await search_repo.find_candidate_documents(
            session, DocumentFilter(date_from=date(2023, 1, 1))
        )

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_date_to_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        await search_repo.find_candidate_documents(
            session, DocumentFilter(date_to=date(2024, 12, 31))
        )

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_category_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        await search_repo.find_candidate_documents(
            session, DocumentFilter(category="kyrklig")
        )

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_entity_names_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        await search_repo.find_candidate_documents(
            session, DocumentFilter(entity_names=["kyrkorådet"])
        )

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_references_case_number_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        await search_repo.find_candidate_documents(
            session, DocumentFilter(references_case_number="123/2020")
        )

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_list_of_uuids(self):
        session = _make_session()
        ids = [uuid.uuid4(), uuid.uuid4()]
        session.execute.return_value = _scalars_result(ids)

        result = await search_repo.find_candidate_documents(session, DocumentFilter())

        assert result == ids


class TestChunkSearch:
    def _make_chunk_row(self, score: float) -> SimpleNamespace:
        chunk = SimpleNamespace(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_text="test chunk",
            chunk_index=0,
            section="body",
            appendix_label=None,
        )
        return SimpleNamespace(Chunk=chunk, score=score)

    @pytest.mark.asyncio
    async def test_vector_search_returns_chunk_results(self):
        session = _make_session()
        row = self._make_chunk_row(score=0.1)
        session.execute.return_value = _rows_result([row])

        results = await chunk_repo.vector_search(
            session, embedding=[0.1, 0.2], document_ids=None
        )

        assert len(results) == 1
        assert isinstance(results[0], ChunkSearchResult)
        assert results[0].chunk_text == "test chunk"
        assert results[0].score == 0.1

    @pytest.mark.asyncio
    async def test_vector_search_with_document_ids(self):
        session = _make_session()
        session.execute.return_value = _rows_result([])

        doc_ids = [uuid.uuid4()]
        await chunk_repo.vector_search(session, embedding=[0.1], document_ids=doc_ids)

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_search_without_document_ids(self):
        session = _make_session()
        session.execute.return_value = _rows_result([])

        await chunk_repo.vector_search(session, embedding=[0.1], document_ids=None)

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_search_returns_chunk_results(self):
        session = _make_session()
        row = self._make_chunk_row(score=0.75)
        session.execute.return_value = _rows_result([row])

        results = await chunk_repo.text_search(
            session, query="kyrklig förvaltning", document_ids=None
        )

        assert len(results) == 1
        assert isinstance(results[0], ChunkSearchResult)
        assert results[0].score == 0.75

    @pytest.mark.asyncio
    async def test_text_search_with_document_ids(self):
        session = _make_session()
        session.execute.return_value = _rows_result([])

        doc_ids = [uuid.uuid4(), uuid.uuid4()]
        await chunk_repo.text_search(session, query="test", document_ids=doc_ids)

        session.execute.assert_called_once()
