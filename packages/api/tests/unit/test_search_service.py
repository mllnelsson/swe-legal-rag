from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from ai.dtos import QueryExpansionResult
from api.config import SearchSettings
from api.services.search_service import SearchQuery, search_documents
from shared.dtos.document import DocumentRead
from shared.dtos.search import ChunkSearchResult, DocumentFilter
from shared.enums import ChunkSection


def _settings(
    *,
    search_default_limit: int = 10,
    search_max_limit: int = 50,
    search_arm_limit: int = 50,
    search_chunks_per_document: int = 3,
    search_candidate_limit: int = 500,
    search_max_query_variants: int = 3,
    search_expand_vector_arm: bool = False,
) -> SearchSettings:
    """Search settings with test defaults.

    Spelled out rather than splatted, for the reason recorded in
    `test_retriever._settings`: a `**kwargs` splat matches every keyword-only
    parameter on `BaseSettings.__init__` and protects against nothing.
    """
    return SearchSettings(
        search_default_limit=search_default_limit,
        search_max_limit=search_max_limit,
        search_arm_limit=search_arm_limit,
        search_chunks_per_document=search_chunks_per_document,
        search_candidate_limit=search_candidate_limit,
        search_max_query_variants=search_max_query_variants,
        search_expand_vector_arm=search_expand_vector_arm,
    )


def _chunk(
    document_id: uuid.UUID, text: str = "chunk text", index: int = 0
) -> ChunkSearchResult:
    return ChunkSearchResult(
        id=uuid.uuid4(),
        document_id=document_id,
        chunk_text=text,
        chunk_index=index,
        score=0.5,
        section=ChunkSection.BODY,
    )


def _doc(document_id: uuid.UUID) -> DocumentRead:
    now = datetime.now()
    return DocumentRead(
        id=document_id,
        source_url="https://example.com/beslut.pdf",
        source_document_id=None,
        source_headline="Beslut om utlämnande",
        source_published_at=None,
        gcs_uri="gs://bucket/key",
        raw_text="text",
        summary="Nämnden avslår överklagandet.",
        case_number="2024-0142",
        decision_number="12/2024",
        decision_date=date(2024, 5, 3),
        decision_outcome="avslår överklagandet",
        category="Utlämnande av handlingar",
        created_at=now,
        updated_at=now,
    )


def _embedding_provider() -> MagicMock:
    provider = MagicMock()
    provider.embed = AsyncMock(return_value=[[0.1, 0.2]])
    return provider


class TestFilterHandling:
    async def test_filter_matching_nothing_returns_empty_without_searching(self):
        """A search tool must not answer a narrowed question with wider results.

        Chat deliberately widens to an unfiltered search; here that would mean
        answering "nothing older than 2024" with 2019 decisions.
        """
        with (
            patch("api.services.search_service.search_repo") as mock_search,
            patch("api.services.search_service.chunk_repo") as mock_chunk,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[])
            mock_chunk.vector_search = AsyncMock()
            mock_chunk.text_search = AsyncMock()

            result = await search_documents(
                SearchQuery(
                    query="utlämnande",
                    filter=DocumentFilter(date_from=date(2024, 1, 1)),
                ),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert result.items == []
        assert result.total == 0
        assert result.diagnostics.filter_applied is True
        assert result.diagnostics.candidate_document_count == 0
        mock_chunk.vector_search.assert_not_called()
        mock_chunk.text_search.assert_not_called()

    async def test_an_empty_candidate_set_costs_no_expansion_or_embedding(self):
        """The cheap SQL check runs first so a doomed search pays for nothing."""
        provider = _embedding_provider()
        with (
            patch("api.services.search_service.search_repo") as mock_search,
            patch("api.services.search_service.chunk_repo"),
            patch("api.services.search_service.ai.expand_query") as mock_expand,
        ):
            mock_search.find_candidate_documents = AsyncMock(return_value=[])

            result = await search_documents(
                SearchQuery(
                    query="utlämnande",
                    expand=True,
                    filter=DocumentFilter(date_from=date(2099, 1, 1)),
                ),
                MagicMock(),
                embedding_provider=provider,
                settings=_settings(),
            )

        mock_expand.assert_not_called()
        provider.embed.assert_not_called()
        assert result.effective_queries == ["utlämnande"]
        assert result.diagnostics.expanded is False

    async def test_empty_filter_skips_the_candidate_lookup(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.search_repo") as mock_search,
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_search.find_candidate_documents = AsyncMock()
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande"),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        mock_search.find_candidate_documents.assert_not_called()
        assert result.diagnostics.filter_applied is False
        assert result.diagnostics.candidate_document_count is None


class TestResultShape:
    async def test_hits_are_grouped_per_document_with_metadata_and_chunks(self):
        document_id = uuid.uuid4()
        chunks = [
            _chunk(document_id, text="första stycket", index=0),
            _chunk(document_id, text="andra stycket", index=1),
        ]
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=chunks)
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande"),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert len(result.items) == 1
        hit = result.items[0]
        assert hit.document_id == document_id
        assert hit.case_number == "2024-0142"
        assert hit.decision_number == "12/2024"
        assert hit.summary == "Nämnden avslår överklagandet."
        assert hit.headline == "Beslut om utlämnande"
        assert hit.matched_chunk_count == 2
        # Full chunk text, not an excerpt: the point is to verify the ranking.
        assert [chunk.text for chunk in hit.chunks] == [
            "första stycket",
            "andra stycket",
        ]

    async def test_chunks_per_document_caps_returned_chunks_but_not_the_count(self):
        document_id = uuid.uuid4()
        chunks = [_chunk(document_id, index=i) for i in range(5)]
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=chunks)
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande", chunks_per_document=2),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert len(result.items[0].chunks) == 2
        assert result.items[0].matched_chunk_count == 5

    async def test_arm_ranks_record_which_arm_found_each_chunk(self):
        document_id = uuid.uuid4()
        vector_only = _chunk(document_id, text="vector only")
        both = _chunk(document_id, text="both arms")
        text_only = _chunk(document_id, text="text only")

        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[vector_only, both])
            mock_chunk.text_search = AsyncMock(return_value=[both, text_only])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande"),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        by_id = {chunk.chunk_id: chunk for chunk in result.items[0].chunks}
        assert by_id[vector_only.id].vector_rank == 1
        assert by_id[vector_only.id].text_rank is None
        assert by_id[both.id].vector_rank == 2
        assert by_id[both.id].text_rank == 1
        assert by_id[text_only.id].vector_rank is None
        assert by_id[text_only.id].text_rank == 2

    async def test_documents_are_ordered_by_best_chunk_score(self):
        weak_id, strong_id = uuid.uuid4(), uuid.uuid4()
        strong = _chunk(strong_id, text="strong")
        weak = _chunk(weak_id, text="weak")

        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            # Both arms rank `strong` first, so it accumulates the higher score.
            mock_chunk.vector_search = AsyncMock(return_value=[strong, weak])
            mock_chunk.text_search = AsyncMock(return_value=[strong, weak])
            mock_doc.get_by_id = AsyncMock(side_effect=lambda _s, doc_id: _doc(doc_id))

            result = await search_documents(
                SearchQuery(query="utlämnande"),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert [hit.document_id for hit in result.items] == [strong_id, weak_id]
        assert result.items[0].score > result.items[1].score


class TestAppendixHandling:
    async def test_body_only_by_default(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            await search_documents(
                SearchQuery(query="utlämnande"),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert mock_chunk.vector_search.call_args.kwargs["sections"] == [
            ChunkSection.BODY
        ]

    async def test_include_appendices_searches_every_section(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            await search_documents(
                SearchQuery(query="utlämnande", include_appendices=True),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert mock_chunk.vector_search.call_args.kwargs["sections"] is None

    async def test_empty_body_result_widens_to_appendices_and_says_so(self):
        document_id = uuid.uuid4()
        appendix_chunk = _chunk(document_id, text="bilaga")

        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            # First pass (body only) finds nothing; the widened pass finds a chunk.
            mock_chunk.vector_search = AsyncMock(side_effect=[[], [appendix_chunk]])
            mock_chunk.text_search = AsyncMock(side_effect=[[], []])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande"),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert result.diagnostics.widened_to_appendices is True
        assert len(result.items) == 1


class TestQueryExpansion:
    async def test_expansion_off_makes_no_llm_call(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
            patch("api.services.search_service.ai.expand_query") as mock_expand,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande"),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        mock_expand.assert_not_called()
        assert result.effective_queries == ["utlämnande"]
        assert result.diagnostics.expanded is False

    async def test_expansion_adds_variants_and_keeps_the_original_first(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
            patch(
                "api.services.search_service.ai.expand_query",
                new=AsyncMock(
                    return_value=QueryExpansionResult(
                        variants=["allmänna handlingar", "offentlighetsprincipen"]
                    )
                ),
            ),
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande", expand=True),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert result.effective_queries[0] == "utlämnande"
        assert "allmänna handlingar" in result.effective_queries
        assert result.diagnostics.expanded is True
        # One text arm per query; the vector arm stays on the original alone.
        assert mock_chunk.text_search.await_count == 3
        assert mock_chunk.vector_search.await_count == 1

    async def test_explicit_queries_are_used_without_calling_the_expander(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
            patch("api.services.search_service.ai.expand_query") as mock_expand,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(
                    query="utlämnande",
                    queries=["allmänna handlingar"],
                    expand=True,
                ),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        mock_expand.assert_not_called()
        assert result.effective_queries == ["utlämnande", "allmänna handlingar"]
        assert result.diagnostics.expanded is False

    async def test_variants_are_deduplicated_against_the_original(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(
                    query="utlämnande",
                    queries=["  UTLÄMNANDE ", "", "allmänna handlingar"],
                ),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert result.effective_queries == ["utlämnande", "allmänna handlingar"]

    async def test_variants_are_capped(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="q", queries=["a", "b", "c", "d", "e"]),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(search_max_query_variants=2),
            )

        assert result.effective_queries == ["q", "a", "b"]

    async def test_expander_failure_degrades_to_the_original_query(self):
        """Losing expansion costs recall, not results — as with the reranker."""
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
            patch(
                "api.services.search_service.ai.expand_query",
                new=AsyncMock(side_effect=RuntimeError("provider down")),
            ),
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande", expand=True),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert result.effective_queries == ["utlämnande"]
        assert result.diagnostics.expanded is False
        assert len(result.items) == 1

    async def test_expand_vector_arm_setting_embeds_every_variant(self):
        document_id = uuid.uuid4()
        provider = MagicMock()
        provider.embed = AsyncMock(return_value=[[0.1], [0.2]])
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            await search_documents(
                SearchQuery(query="utlämnande", queries=["allmänna handlingar"]),
                MagicMock(),
                embedding_provider=provider,
                settings=_settings(search_expand_vector_arm=True),
            )

        embedded_texts = provider.embed.await_args_list[0].args[0]
        assert len(embedded_texts) == 2
        assert mock_chunk.vector_search.await_count == 2


class TestDeterminism:
    async def test_expanded_search_is_reproducible_by_replaying_its_queries(self):
        """The guarantee that keeps the core deterministic despite the LLM flag."""
        document_id = uuid.uuid4()
        variants = ["allmänna handlingar", "offentlighetsprincipen"]

        async def run(query: SearchQuery):
            with (
                patch("api.services.search_service.chunk_repo") as mock_chunk,
                patch("api.services.search_service.document_repo") as mock_doc,
                patch(
                    "api.services.search_service.ai.expand_query",
                    new=AsyncMock(return_value=QueryExpansionResult(variants=variants)),
                ),
            ):
                mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
                mock_chunk.text_search = AsyncMock(return_value=[])
                mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))
                return await search_documents(
                    query,
                    MagicMock(),
                    embedding_provider=_embedding_provider(),
                    settings=_settings(),
                )

        expanded = await run(SearchQuery(query="utlämnande", expand=True))
        replayed = await run(
            SearchQuery(query="utlämnande", queries=expanded.effective_queries[1:])
        )

        assert replayed.effective_queries == expanded.effective_queries
        assert [hit.document_id for hit in replayed.items] == [
            hit.document_id for hit in expanded.items
        ]
        assert [hit.score for hit in replayed.items] == [
            hit.score for hit in expanded.items
        ]


class TestPaging:
    async def test_limit_is_clamped_to_the_configured_maximum(self):
        document_id = uuid.uuid4()
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=[_chunk(document_id)])
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(return_value=_doc(document_id))

            result = await search_documents(
                SearchQuery(query="utlämnande", limit=9999),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(search_max_limit=5),
            )

        assert result.limit == 5

    async def test_total_counts_every_matched_document_not_the_page(self):
        document_ids = [uuid.uuid4() for _ in range(4)]
        chunks = [_chunk(document_id) for document_id in document_ids]
        with (
            patch("api.services.search_service.chunk_repo") as mock_chunk,
            patch("api.services.search_service.document_repo") as mock_doc,
        ):
            mock_chunk.vector_search = AsyncMock(return_value=chunks)
            mock_chunk.text_search = AsyncMock(return_value=[])
            mock_doc.get_by_id = AsyncMock(side_effect=lambda _s, doc_id: _doc(doc_id))

            result = await search_documents(
                SearchQuery(query="utlämnande", limit=2),
                MagicMock(),
                embedding_provider=_embedding_provider(),
                settings=_settings(),
            )

        assert result.total == 4
        assert len(result.items) == 2
