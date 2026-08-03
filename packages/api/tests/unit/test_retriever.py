from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.config import RetrievalSettings
from api.services.query_planner import QueryPlan
from api.services.retriever import RetrievedChunk, retrieve
from shared.dtos.document import DocumentRead
from shared.dtos.search import ChunkSearchResult, DocumentFilter
from shared.enums import ChunkSection


def _settings(
    *,
    retrieval_top_k: int = 4,
    retrieval_search_limit: int = 10,
    retrieval_rerank_enabled: bool = False,
    retrieval_include_appendices: bool = False,
) -> RetrievalSettings:
    """Retrieval settings with test defaults.

    Spelled out rather than `**kwargs` into a dict splat: the splat matched every
    keyword-only parameter on `BaseSettings.__init__` (`_env_file`,
    `_cli_settings_source`, …), which is 27 type errors and no protection against
    a misspelled field name.
    """
    return RetrievalSettings(
        retrieval_top_k=retrieval_top_k,
        retrieval_search_limit=retrieval_search_limit,
        retrieval_rerank_enabled=retrieval_rerank_enabled,
        retrieval_include_appendices=retrieval_include_appendices,
    )


def _plan(query: str = "kyrkorätt", **filter_kwargs) -> QueryPlan:
    return QueryPlan(semantic_query=query, filter=DocumentFilter(**filter_kwargs))


def _chunk(
    document_id: uuid.UUID | None = None, text: str = "chunk text"
) -> ChunkSearchResult:
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
        source_document_id=None,
        source_headline=None,
        source_published_at=None,
        gcs_uri=None,
        raw_text="text",
        summary=None,
        case_number="2023/001",
        decision_number=None,
        decision_date=date(2023, 3, 15),
        decision_outcome="bifaller",
        category="Kyrkogård",
        created_at=__import__("datetime").datetime.now(),
        updated_at=__import__("datetime").datetime.now(),
    )


class TestRetrieve:
    def _make_embedding_provider(
        self, embedding: list[float] | None = None
    ) -> MagicMock:
        provider = MagicMock()
        provider.embed = AsyncMock(return_value=[embedding or [0.1, 0.2]])
        return provider

    @pytest.mark.asyncio
    async def test_empty_filter_skips_find_candidates(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
        ):
            mock_search.find_candidate_documents = AsyncMock()
            mock_chunk.vector_search = AsyncMock(return_value=[chunk])
            mock_chunk.text_search = AsyncMock(return_value=[chunk])
            mock_doc.get_by_id = AsyncMock(return_value=doc)

            plan = _plan()  # empty filter
            result = await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(),
            )

            mock_search.find_candidate_documents.assert_not_called()
            mock_chunk.vector_search.assert_called_once()
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_non_empty_filter_calls_find_candidates(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[doc_id])
            mock_chunk.vector_search = AsyncMock(return_value=[chunk])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=doc)

            plan = _plan(category="Kyrkogård")
            await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(),
            )

            mock_search.find_candidate_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_unfiltered_when_candidates_empty(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[])
            mock_chunk.vector_search = AsyncMock(return_value=[chunk])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=doc)

            plan = _plan(category="Kyrkogård")
            await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(),
            )

            # vector_search and text_search should be called with document_ids=None (unfiltered).
            # positional args are (session, embedding, document_ids); document_ids is args[2].
            call_kwargs = mock_chunk.vector_search.call_args
            assert (
                call_kwargs.args[2] is None
                or call_kwargs.kwargs.get("document_ids") is None
            )

    @pytest.mark.asyncio
    async def test_rerank_not_called_when_disabled(self):
        doc_id = uuid.uuid4()
        chunk = _chunk(document_id=doc_id)
        doc = _doc(doc_id)

        with (
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
            patch("api.services.retriever._rerank") as mock_rerank,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[])
            mock_chunk.vector_search = AsyncMock(return_value=[chunk])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=doc)

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
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
            patch(
                "api.services.retriever._rerank", new=AsyncMock(return_value=[chunk])
            ) as mock_rerank,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[])
            mock_chunk.vector_search = AsyncMock(return_value=[chunk])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=doc)

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
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[])
            mock_chunk.vector_search = AsyncMock(return_value=[chunk])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=doc)

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
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[])
            mock_chunk.vector_search = AsyncMock(return_value=[chunk])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=doc)

            # Patched rather than asserted against the shipped value: what
            # matters is that the prefix comes from the configured pair, so it
            # cannot drift from the passage half worker-embed applies.
            with patch(
                "api.services.retriever.get_embedding_prefixes",
                return_value=("fråga: ", "stycke: "),
            ):
                plan = _plan(query="kyrkorätt")
                await retrieve(
                    plan, MagicMock(), embedding_provider=provider, settings=_settings()
                )

            provider.embed.assert_called_once_with(["fråga: kyrkorätt"])


class TestSectionScoping:
    """Appendices hold the appealed decision, so they are out of the default search.

    A hard predicate rather than a ranking tweak, because every chunk embeds the
    body-derived summary via contextual_text — similarity alone cannot tell the
    nämnd's reasoning from the instance below it.
    """

    def _make_embedding_provider(self) -> MagicMock:
        provider = MagicMock()
        provider.embed = AsyncMock(return_value=[[0.1, 0.2]])
        return provider

    async def _retrieve(self, plan: QueryPlan, settings: RetrievalSettings, **results):
        doc_id = uuid.uuid4()
        with (
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[doc_id])
            mock_chunk.vector_search = AsyncMock(
                side_effect=results.get("vector", [[_chunk(document_id=doc_id)]])
            )
            mock_chunk.text_search = AsyncMock(side_effect=results.get("text", [[]]))
            mock_doc.get_by_id = AsyncMock(return_value=_doc(doc_id))
            await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=settings,
            )
            return mock_chunk

    @pytest.mark.asyncio
    async def test_default_search_is_body_only(self):
        mock_chunk = await self._retrieve(_plan(), _settings())
        assert mock_chunk.vector_search.call_args.kwargs["sections"] == [
            ChunkSection.BODY
        ]
        assert mock_chunk.text_search.call_args.kwargs["sections"] == [
            ChunkSection.BODY
        ]

    @pytest.mark.asyncio
    async def test_planner_can_widen_to_appendices(self):
        plan = QueryPlan(
            semantic_query="vad beslutade stiftet?",
            filter=DocumentFilter(),
            include_appendices=True,
        )
        mock_chunk = await self._retrieve(plan, _settings())
        assert mock_chunk.vector_search.call_args.kwargs["sections"] is None

    @pytest.mark.asyncio
    async def test_setting_can_widen_to_appendices(self):
        settings = _settings(retrieval_include_appendices=True)
        mock_chunk = await self._retrieve(_plan(), settings)
        assert mock_chunk.vector_search.call_args.kwargs["sections"] is None

    @pytest.mark.asyncio
    async def test_widens_when_body_only_finds_nothing(self):
        # First pass body-only returns nothing; the retry drops the restriction.
        doc_id = uuid.uuid4()
        mock_chunk = await self._retrieve(
            _plan(),
            _settings(),
            vector=[[], [_chunk(document_id=doc_id)]],
            text=[[], []],
        )
        assert mock_chunk.vector_search.call_count == 2
        first, second = mock_chunk.vector_search.call_args_list
        assert first.kwargs["sections"] == [ChunkSection.BODY]
        assert second.kwargs["sections"] is None

    @pytest.mark.asyncio
    async def test_does_not_widen_when_body_matched(self):
        mock_chunk = await self._retrieve(_plan(), _settings())
        assert mock_chunk.vector_search.call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_when_already_unrestricted(self):
        settings = _settings(retrieval_include_appendices=True)
        mock_chunk = await self._retrieve(
            _plan(), settings, vector=[[], []], text=[[], []]
        )
        assert mock_chunk.vector_search.call_count == 1

    @pytest.mark.asyncio
    async def test_section_is_carried_onto_the_retrieved_chunk(self):
        doc_id = uuid.uuid4()
        appendix_chunk = ChunkSearchResult(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_text="underinstansens skäl",
            chunk_index=0,
            score=0.5,
            section=ChunkSection.APPENDIX,
            appendix_label="Bilaga A",
        )
        with (
            patch("api.services.retriever.search_repo") as mock_search,
            patch("api.services.retriever.chunk_repo") as mock_chunk,
            patch("api.services.retriever.document_repo") as mock_doc,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[doc_id])
            mock_chunk.vector_search = AsyncMock(return_value=[appendix_chunk])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(doc_id))

            plan = QueryPlan(
                semantic_query="q", filter=DocumentFilter(), include_appendices=True
            )
            result = await retrieve(
                plan,
                MagicMock(),
                embedding_provider=self._make_embedding_provider(),
                settings=_settings(),
            )

        assert result[0].section is ChunkSection.APPENDIX
        assert result[0].appendix_label == "Bilaga A"
