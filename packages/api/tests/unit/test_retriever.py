from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.config import RetrievalSettings
from api.services.query_planner import QueryPlan
from api.services.retriever import RetrievedChunk, _filter_is_empty, retrieve
from shared.dtos.document import DocumentRead
from shared.dtos.search import ChunkSearchResult, DocumentFilter


def _settings(**kwargs) -> RetrievalSettings:
    defaults = dict(retrieval_top_k=4, retrieval_search_limit=10, retrieval_rerank_enabled=False)
    return RetrievalSettings(**{**defaults, **kwargs})


def _plan(query: str = "kyrkorätt", **filter_kwargs) -> QueryPlan:
    return QueryPlan(semantic_query=query, filter=DocumentFilter(**filter_kwargs))


def _chunk(document_id: uuid.UUID | None = None, text: str = "chunk text") -> ChunkSearchResult:
    return ChunkSearchResult(
        id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        chunk_text=text,
        chunk_index=0,
        score=0.5,
    )


def _doc(doc_id: uuid.UUID) -> DocumentRead:
    return DocumentRead(
        id=doc_id,
        source_url="http://example.com/doc.pdf",
        gcs_uri=None,
        raw_text="text",
        summary=None,
        case_number="2023/001",
        decision_date=date(2023, 3, 15),
        decision_outcome="bifaller",
        category="Kyrkogård",
        created_at=__import__("datetime").datetime.now(),
        updated_at=__import__("datetime").datetime.now(),
    )


class TestFilterIsEmpty:
    def test_empty_filter_is_empty(self):
        assert _filter_is_empty(DocumentFilter()) is True

    def test_date_from_makes_non_empty(self):
        assert _filter_is_empty(DocumentFilter(date_from=date(2023, 1, 1))) is False

    def test_category_makes_non_empty(self):
        assert _filter_is_empty(DocumentFilter(category="Kyrkogård")) is False

    def test_entity_names_makes_non_empty(self):
        assert _filter_is_empty(DocumentFilter(entity_names=["kyrkorådet"])) is False

    def test_entity_types_makes_non_empty(self):
        assert _filter_is_empty(DocumentFilter(entity_types=["PERSON"])) is False

    def test_references_case_number_makes_non_empty(self):
        assert _filter_is_empty(DocumentFilter(references_case_number="123/2020")) is False


class TestRetrieve:
    def _make_embedding_provider(self, embedding: list[float] | None = None) -> MagicMock:
        provider = MagicMock()
        provider.embed = AsyncMock(return_value=[embedding or [0.1, 0.2]])
        return provider

    @pytest.mark.asyncio
    async def test_empty_filter_skips_find_candidates(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.SearchRepository") as MockSearch,
            patch("api.services.retriever.ChunkRepository") as MockChunk,
            patch("api.services.retriever.DocumentRepository") as MockDoc,
        ):
            MockSearch.return_value.find_candidate_documents = AsyncMock()
            MockChunk.return_value.vector_search = AsyncMock(return_value=[chunk])
            MockChunk.return_value.text_search = AsyncMock(return_value=[chunk])
            MockDoc.return_value.get_by_id = AsyncMock(return_value=doc)

            plan = _plan()  # empty filter
            result = await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(),
            )

            MockSearch.return_value.find_candidate_documents.assert_not_called()
            MockChunk.return_value.vector_search.assert_called_once()
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_non_empty_filter_calls_find_candidates(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.SearchRepository") as MockSearch,
            patch("api.services.retriever.ChunkRepository") as MockChunk,
            patch("api.services.retriever.DocumentRepository") as MockDoc,
        ):
            MockSearch.return_value.find_candidate_documents = AsyncMock(return_value=[doc_id])
            MockChunk.return_value.vector_search = AsyncMock(return_value=[chunk])
            MockChunk.return_value.text_search = AsyncMock(return_value=[])
            MockDoc.return_value.get_by_id = AsyncMock(return_value=doc)

            plan = _plan(category="Kyrkogård")
            await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(),
            )

            MockSearch.return_value.find_candidate_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_unfiltered_when_candidates_empty(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.SearchRepository") as MockSearch,
            patch("api.services.retriever.ChunkRepository") as MockChunk,
            patch("api.services.retriever.DocumentRepository") as MockDoc,
        ):
            MockSearch.return_value.find_candidate_documents = AsyncMock(return_value=[])
            MockChunk.return_value.vector_search = AsyncMock(return_value=[chunk])
            MockChunk.return_value.text_search = AsyncMock(return_value=[])
            MockDoc.return_value.get_by_id = AsyncMock(return_value=doc)

            plan = _plan(category="Kyrkogård")
            await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(),
            )

            # vector_search and text_search should be called with document_ids=None (unfiltered)
            call_kwargs = MockChunk.return_value.vector_search.call_args
            assert call_kwargs.args[1] is None or call_kwargs.kwargs.get("document_ids") is None

    @pytest.mark.asyncio
    async def test_rerank_not_called_when_disabled(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.SearchRepository") as MockSearch,
            patch("api.services.retriever.ChunkRepository") as MockChunk,
            patch("api.services.retriever.DocumentRepository") as MockDoc,
            patch("api.services.retriever._rerank") as mock_rerank,
        ):
            MockSearch.return_value.find_candidate_documents = AsyncMock(return_value=[])
            MockChunk.return_value.vector_search = AsyncMock(return_value=[chunk])
            MockChunk.return_value.text_search = AsyncMock(return_value=[])
            MockDoc.return_value.get_by_id = AsyncMock(return_value=doc)

            plan = _plan()
            await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(retrieval_rerank_enabled=False),
            )

            mock_rerank.assert_not_called()

    @pytest.mark.asyncio
    async def test_rerank_called_when_enabled(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.SearchRepository") as MockSearch,
            patch("api.services.retriever.ChunkRepository") as MockChunk,
            patch("api.services.retriever.DocumentRepository") as MockDoc,
            patch("api.services.retriever._rerank", new=AsyncMock(return_value=[chunk])) as mock_rerank,
        ):
            MockSearch.return_value.find_candidate_documents = AsyncMock(return_value=[])
            MockChunk.return_value.vector_search = AsyncMock(return_value=[chunk])
            MockChunk.return_value.text_search = AsyncMock(return_value=[])
            MockDoc.return_value.get_by_id = AsyncMock(return_value=doc)

            plan = _plan()
            await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(retrieval_rerank_enabled=True),
            )

            mock_rerank.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_retrieved_chunks_with_doc_metadata(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.SearchRepository") as MockSearch,
            patch("api.services.retriever.ChunkRepository") as MockChunk,
            patch("api.services.retriever.DocumentRepository") as MockDoc,
        ):
            MockSearch.return_value.find_candidate_documents = AsyncMock(return_value=[])
            MockChunk.return_value.vector_search = AsyncMock(return_value=[chunk])
            MockChunk.return_value.text_search = AsyncMock(return_value=[])
            MockDoc.return_value.get_by_id = AsyncMock(return_value=doc)

            plan = _plan()
            result = await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(),
            )

            assert len(result) == 1
            assert isinstance(result[0], RetrievedChunk)
            assert result[0].case_number == "2023/001"
            assert result[0].decision_date == date(2023, 3, 15)
            assert result[0].category == "Kyrkogård"

    @pytest.mark.asyncio
    async def test_query_embedded_with_e5_prefix(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)
        provider = self._make_embedding_provider()

        with (
            patch("api.services.retriever.SearchRepository") as MockSearch,
            patch("api.services.retriever.ChunkRepository") as MockChunk,
            patch("api.services.retriever.DocumentRepository") as MockDoc,
        ):
            MockSearch.return_value.find_candidate_documents = AsyncMock(return_value=[])
            MockChunk.return_value.vector_search = AsyncMock(return_value=[chunk])
            MockChunk.return_value.text_search = AsyncMock(return_value=[])
            MockDoc.return_value.get_by_id = AsyncMock(return_value=doc)

            plan = _plan(query="kyrkorätt")
            await retrieve(plan, MagicMock(), embedding_provider=provider, settings=_settings())

            provider.embed.assert_called_once_with(["query: kyrkorätt"])
