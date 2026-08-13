"""The seam between the agent's shapes and the deterministic services.

The agent is covered against a fake toolset in `packages/agents`; what is left
to prove here is that the real one hands it the same things — in particular the
two fields the agent reasons with that a naive mapping would drop.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from shared.dtos.search import DocumentFacets, DocumentFilter, FacetValue
from shared.enums import ChunkSection
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import SearchSettings
from api.pagination import Page
from api.services.chat_toolset import build_chat_toolset
from api.services.document_service import (
    DocumentChunk,
    DocumentDetail,
    DocumentSections,
    DocumentSummary,
)
from api.services.search_service import (
    SearchChunk,
    SearchDiagnostics,
    SearchHit,
    SearchResponse,
)

_DOCUMENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_CHUNK_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _toolset():
    return build_chat_toolset(
        MagicMock(spec=AsyncSession),
        embedding_provider=MagicMock(),
        search_settings=SearchSettings(),
        sql_llm_provider=MagicMock(),
    )


def _search_response() -> SearchResponse:
    return SearchResponse(
        items=[
            SearchHit(
                document_id=_DOCUMENT_ID,
                case_number="12/2024",
                decision_number="12/2024",
                decision_date=None,
                category="Tjänstetillsättning",
                decision_outcome="Avslag",
                headline=None,
                summary="En sammanfattning.",
                source_url="https://example.test/1",
                score=0.0164,
                matched_chunk_count=1,
                chunks=[
                    SearchChunk(
                        chunk_id=_CHUNK_ID,
                        chunk_index=3,
                        text="Nämnden avslår överklagandet.",
                        section=ChunkSection.APPENDIX,
                        appendix_label="Bilaga A",
                        score=0.0164,
                        vector_rank=1,
                        text_rank=None,
                        vector_similarity=0.86,
                        text_score=None,
                    )
                ],
            )
        ],
        total=1,
        limit=10,
        offset=0,
        effective_queries=["jäv"],
        diagnostics=SearchDiagnostics(
            filter_applied=True,
            candidate_document_count=41,
            vector_hit_count=1,
            text_hit_counts={"jäv": 0},
            fused_chunk_count=1,
            expanded=False,
            widened_to_appendices=True,
            vector_similarity_floor=0.78,
            top_vector_similarity=0.86,
        ),
    )


def _document_detail() -> DocumentDetail:
    return DocumentDetail(
        document=DocumentSummary(
            document_id=_DOCUMENT_ID,
            case_number="12/2024",
            decision_number="12/2024",
            decision_date=None,
            category=None,
            decision_outcome=None,
            headline=None,
            summary=None,
            source_url="https://example.test/1",
            source_published_at=None,
            has_pdf=True,
        ),
        sections=DocumentSections(
            body_chunk_count=1, appendix_chunk_count=1, appendix_labels=["Bilaga A"]
        ),
        keywords=[],
        concepts=[],
        regulations=[],
        roles=[],
        parishes=[],
        other_entities=[],
        references_out=[],
        references_in=[],
        unresolved_references=[],
    )


class TestSearchMapping:
    async def test_similarity_and_diagnostics_reach_the_agent(self):
        """Both are what let the agent say the corpus does not address a question.

        `score` cannot: RRF derives it from rank alone, so the top hit scores the
        same whatever was asked.
        """
        with patch(
            "api.services.chat_toolset.search_documents",
            AsyncMock(return_value=_search_response()),
        ):
            outcome = await _toolset().search(
                query="jäv",
                queries=[],
                document_filter=DocumentFilter(),
                include_appendices=False,
                limit=8,
                chunks_per_decision=2,
            )

        assert outcome.top_vector_similarity == 0.86
        assert outcome.candidate_document_count == 41
        assert outcome.widened_to_appendices is True
        assert outcome.decisions[0].chunks[0].vector_similarity == 0.86

    async def test_appendix_provenance_survives_the_mapping(self):
        with patch(
            "api.services.chat_toolset.search_documents",
            AsyncMock(return_value=_search_response()),
        ):
            outcome = await _toolset().search(
                query="jäv",
                queries=[],
                document_filter=DocumentFilter(),
                include_appendices=False,
                limit=8,
                chunks_per_decision=2,
            )

        chunk = outcome.decisions[0].chunks[0]
        assert chunk.section is ChunkSection.APPENDIX
        assert chunk.appendix_label == "Bilaga A"

    async def test_agent_phrasings_are_passed_through_not_expanded(self):
        """The agent has already rephrased; paying a model to do it again is waste."""
        search = AsyncMock(return_value=_search_response())
        with patch("api.services.chat_toolset.search_documents", search):
            await _toolset().search(
                query="jäv",
                queries=["intressekonflikt"],
                document_filter=DocumentFilter(),
                include_appendices=False,
                limit=8,
                chunks_per_decision=2,
            )

        call = search.await_args
        assert call is not None
        query = call.args[0]
        assert query.queries == ["intressekonflikt"]
        assert query.expand is False


class TestDecisionText:
    async def test_body_only_by_default(self):
        chunks = AsyncMock(
            return_value=[
                DocumentChunk(
                    chunk_id=_CHUNK_ID,
                    chunk_index=0,
                    text="Nämndens text.",
                    section=ChunkSection.BODY,
                    appendix_label=None,
                )
            ]
        )
        with (
            patch(
                "api.services.chat_toolset.document_service.get_document_detail",
                AsyncMock(return_value=_document_detail()),
            ),
            patch(
                "api.services.chat_toolset.document_service.get_document_chunks", chunks
            ),
        ):
            text = await _toolset().decision_text(
                document_id=_DOCUMENT_ID, include_appendices=False
            )

        call = chunks.await_args
        assert call is not None
        assert call.kwargs["section"] is ChunkSection.BODY
        assert text is not None
        assert text.case_number == "12/2024"

    async def test_appendices_are_opt_in(self):
        chunks = AsyncMock(return_value=[])
        with (
            patch(
                "api.services.chat_toolset.document_service.get_document_detail",
                AsyncMock(return_value=_document_detail()),
            ),
            patch(
                "api.services.chat_toolset.document_service.get_document_chunks", chunks
            ),
        ):
            await _toolset().decision_text(
                document_id=_DOCUMENT_ID, include_appendices=True
            )

        call = chunks.await_args
        assert call is not None
        assert call.kwargs["section"] is None

    async def test_unknown_document_is_none_not_an_error(self):
        with patch(
            "api.services.chat_toolset.document_service.get_document_detail",
            AsyncMock(return_value=None),
        ):
            assert (
                await _toolset().decision_text(
                    document_id=_DOCUMENT_ID, include_appendices=False
                )
                is None
            )


class TestVocabulary:
    async def test_facets_map_to_the_grounding_vocabulary(self):
        facets = DocumentFacets(
            categories=[FacetValue(value="Tjänstetillsättning", count=41)],
            decision_outcomes=[FacetValue(value="Avslag", count=88)],
            entity_types=[],
            keywords=[FacetValue(value="jäv", count=12)],
            earliest_decision_date=None,
            latest_decision_date=None,
            document_count=184,
        )
        with patch(
            "api.services.chat_toolset.get_filters", AsyncMock(return_value=facets)
        ):
            vocabulary = await _toolset().vocabulary()

        assert vocabulary.categories[0].value == "Tjänstetillsättning"
        assert vocabulary.decision_outcomes[0].count == 88
        assert vocabulary.document_count == 184

    async def test_contains_reaches_past_the_facet_cap(self):
        """The facets are capped; `contains` is how the tail is reachable."""
        facets = DocumentFacets(
            categories=[],
            decision_outcomes=[],
            entity_types=[],
            keywords=[],
            earliest_decision_date=None,
            latest_decision_date=None,
            document_count=184,
        )
        keyword = MagicMock(name="jävsregler", document_count=3)
        keyword.name = "jävsregler"

        with (
            patch(
                "api.services.chat_toolset.get_filters", AsyncMock(return_value=facets)
            ),
            patch(
                "api.services.chat_toolset.keyword_service.list_keywords",
                AsyncMock(
                    return_value=Page(items=[keyword], total=1, limit=40, offset=0)
                ),
            ),
            patch(
                "api.services.chat_toolset.concept_service.list_concepts",
                AsyncMock(return_value=Page(items=[], total=0, limit=40, offset=0)),
            ),
        ):
            vocabulary = await _toolset().vocabulary(contains="jäv")

        assert [value.value for value in vocabulary.keywords] == ["jävsregler"]
