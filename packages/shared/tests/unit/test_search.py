import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.dtos.search import ChunkSearchResult, DocumentFilter
from shared.repositories.chunk import ChunkRepository
from shared.repositories.search import SearchRepository


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


class TestSearchRepositoryFindCandidates:
    @pytest.mark.asyncio
    async def test_empty_filter_returns_all_doc_ids(self):
        session = _make_session()
        doc_id = uuid.uuid4()
        session.execute.return_value = _scalars_result([doc_id])

        repo = SearchRepository(session)
        result = await repo.find_candidate_documents(DocumentFilter())

        session.execute.assert_called_once()
        assert result == [doc_id]

    @pytest.mark.asyncio
    async def test_date_from_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        repo = SearchRepository(session)
        await repo.find_candidate_documents(DocumentFilter(date_from=date(2023, 1, 1)))

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_date_to_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        repo = SearchRepository(session)
        await repo.find_candidate_documents(DocumentFilter(date_to=date(2024, 12, 31)))

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_category_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        repo = SearchRepository(session)
        await repo.find_candidate_documents(DocumentFilter(category="kyrklig"))

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_entity_names_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        repo = SearchRepository(session)
        await repo.find_candidate_documents(DocumentFilter(entity_names=["kyrkorådet"]))

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_references_case_number_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalars_result([])

        repo = SearchRepository(session)
        await repo.find_candidate_documents(
            DocumentFilter(references_case_number="123/2020")
        )

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_list_of_uuids(self):
        session = _make_session()
        ids = [uuid.uuid4(), uuid.uuid4()]
        session.execute.return_value = _scalars_result(ids)

        repo = SearchRepository(session)
        result = await repo.find_candidate_documents(DocumentFilter())

        assert result == ids


class TestChunkRepositorySearch:
    def _make_chunk_row(self, score: float) -> SimpleNamespace:
        chunk = SimpleNamespace(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_text="test chunk",
            chunk_index=0,
        )
        return SimpleNamespace(Chunk=chunk, score=score)

    @pytest.mark.asyncio
    async def test_vector_search_returns_chunk_results(self):
        session = _make_session()
        row = self._make_chunk_row(score=0.1)
        session.execute.return_value = _rows_result([row])

        repo = ChunkRepository(session)
        results = await repo.vector_search(embedding=[0.1, 0.2], document_ids=None)

        assert len(results) == 1
        assert isinstance(results[0], ChunkSearchResult)
        assert results[0].chunk_text == "test chunk"
        assert results[0].score == 0.1

    @pytest.mark.asyncio
    async def test_vector_search_with_document_ids(self):
        session = _make_session()
        session.execute.return_value = _rows_result([])

        repo = ChunkRepository(session)
        doc_ids = [uuid.uuid4()]
        await repo.vector_search(embedding=[0.1], document_ids=doc_ids)

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_search_without_document_ids(self):
        session = _make_session()
        session.execute.return_value = _rows_result([])

        repo = ChunkRepository(session)
        await repo.vector_search(embedding=[0.1], document_ids=None)

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_search_returns_chunk_results(self):
        session = _make_session()
        row = self._make_chunk_row(score=0.75)
        session.execute.return_value = _rows_result([row])

        repo = ChunkRepository(session)
        results = await repo.text_search(query="kyrklig förvaltning", document_ids=None)

        assert len(results) == 1
        assert isinstance(results[0], ChunkSearchResult)
        assert results[0].score == 0.75

    @pytest.mark.asyncio
    async def test_text_search_with_document_ids(self):
        session = _make_session()
        session.execute.return_value = _rows_result([])

        repo = ChunkRepository(session)
        doc_ids = [uuid.uuid4(), uuid.uuid4()]
        await repo.text_search(query="test", document_ids=doc_ids)

        session.execute.assert_called_once()
