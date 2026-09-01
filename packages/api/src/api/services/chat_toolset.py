"""The deterministic retrieval tool set, as the conversational agent sees it.

`agents.ChatToolset` declares five capabilities in the agent's own shapes; this
is the one place they are joined to the services that implement them. It lives
here rather than in `agents` because it is the `api` side of that seam — the
dependency runs `api -> agents`, and closing the loop the other way would make a
cycle of it.

A class rather than a module of functions because the Protocol wants an object
carrying its dependencies: one session, one embedding provider, one settings
object, threaded through five calls.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import agents
from agents import ChatToolset
from agents.chat import (
    DecisionProfile,
    DecisionText,
    DecisionTextChunk,
    SearchedChunk,
    SearchedDecision,
    SearchOutcome,
    Vocabulary,
    VocabularyValue,
)
from ai.embedding import EmbeddingProvider
from agent_kit.llm import LLMProvider
from shared.dtos.document_entity import DocumentEntityDetail
from shared.dtos.search import DocumentFacets, DocumentFilter, FacetValue
from shared.enums import ChunkSection, EntityType
from sqlalchemy.ext.asyncio import AsyncSession

from api.access_log import preview
from api.config import SearchSettings
from api.services import concept_service, document_service, keyword_service
from api.services.search_service import (
    SearchHit,
    SearchQuery,
    SearchResponse,
    get_filters,
    search_documents,
)

__all__ = ["ApiChatToolset", "build_chat_toolset"]

# Values one `contains` lookup may return per entity kind. The facets already
# publish the most common; this is the tail behind them.
_ENTITY_LOOKUP_LIMIT = 40


def _facet_values(values: list[FacetValue]) -> list[VocabularyValue]:
    return [VocabularyValue(value=value.value, count=value.count) for value in values]


def _to_searched_decision(hit: SearchHit) -> SearchedDecision:
    return SearchedDecision(
        document_id=hit.document_id,
        case_number=hit.case_number,
        decision_date=hit.decision_date,
        decision_outcome=hit.decision_outcome,
        category=hit.category,
        summary=hit.summary,
        chunks=[
            SearchedChunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                section=chunk.section,
                appendix_label=chunk.appendix_label,
                # Comparable across queries, unlike the fused `score`, which is
                # rank-derived and identical for the top hit of any search. This
                # is the number that lets the agent tell a close match from the
                # nearest paragraph to a question the corpus does not address.
                vector_similarity=chunk.vector_similarity,
            )
            for chunk in hit.chunks
        ],
    )


def _to_search_outcome(response: SearchResponse) -> SearchOutcome:
    return SearchOutcome(
        decisions=[_to_searched_decision(hit) for hit in response.items],
        widened_to_appendices=response.diagnostics.widened_to_appendices,
        candidate_document_count=response.diagnostics.candidate_document_count,
        top_vector_similarity=response.diagnostics.top_vector_similarity,
    )


def _to_vocabulary(facets: DocumentFacets) -> Vocabulary:
    """The facets as the agent sees them.

    `concepts` is absent from `DocumentFacets` and is filled in only by a
    `contains` lookup — the tool says so rather than reporting an empty list as
    if the corpus had no legal concepts in it.
    """
    return Vocabulary(
        categories=_facet_values(facets.categories),
        decision_outcomes=_facet_values(facets.decision_outcomes),
        keywords=_facet_values(facets.keywords),
        document_count=facets.document_count,
        earliest_decision_date=facets.earliest_decision_date,
        latest_decision_date=facets.latest_decision_date,
    )


def _names(entities: list[DocumentEntityDetail]) -> list[str]:
    return [entity.name for entity in entities]


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiChatToolset:
    """`ChatToolset` over the deterministic services."""

    session: AsyncSession
    embedding_provider: EmbeddingProvider
    search_settings: SearchSettings
    sql_llm_provider: LLMProvider | None = None

    async def search(
        self,
        *,
        query: str,
        queries: list[str],
        document_filter: DocumentFilter,
        include_appendices: bool,
        limit: int,
        chunks_per_decision: int,
    ) -> SearchOutcome:
        response = await search_documents(
            SearchQuery(
                query=query,
                # The agent supplies its own rephrasings rather than setting
                # `expand`, which would spend a second model call to produce
                # what it already has an opinion about.
                queries=queries or None,
                filter=document_filter,
                include_appendices=include_appendices,
                limit=limit,
                chunks_per_document=chunks_per_decision,
            ),
            self.session,
            embedding_provider=self.embedding_provider,
            settings=self.search_settings,
        )
        logger.debug(
            "tool search q=%s limit=%d → %d decisions top_sim=%s",
            preview(query),
            limit,
            len(response.items),
            response.diagnostics.top_vector_similarity,
        )
        return _to_search_outcome(response)

    async def vocabulary(self, *, contains: str | None = None) -> Vocabulary:
        facets = await get_filters(self.session)
        vocabulary = _to_vocabulary(facets)
        if contains is None:
            logger.debug(
                "tool vocabulary → %d categories %d keywords",
                len(vocabulary.categories),
                len(vocabulary.keywords),
            )
            return vocabulary

        # The facets are capped, so a `contains` lookup is how the agent reaches
        # a keyword or concept past the most common ones.
        keywords = await keyword_service.list_keywords(
            self.session, name_query=contains, limit=_ENTITY_LOOKUP_LIMIT
        )
        concepts = await concept_service.list_concepts(
            self.session,
            entity_type=EntityType.LEGAL_CONCEPT,
            name_query=contains,
            limit=_ENTITY_LOOKUP_LIMIT,
        )
        logger.debug(
            "tool vocabulary contains=%s → %d keywords %d concepts",
            preview(contains),
            len(keywords.items),
            len(concepts.items),
        )
        return vocabulary.model_copy(
            update={
                "keywords": [
                    VocabularyValue(value=item.name, count=item.document_count)
                    for item in keywords.items
                ],
                "concepts": [
                    VocabularyValue(value=item.name, count=item.document_count)
                    for item in concepts.items
                ],
            }
        )

    async def decision_text(
        self, *, document_id: uuid.UUID, include_appendices: bool
    ) -> DecisionText | None:
        detail = await document_service.get_document_detail(self.session, document_id)
        if detail is None:
            return None
        chunks = await document_service.get_document_chunks(
            self.session,
            document_id,
            section=None if include_appendices else ChunkSection.BODY,
        )
        if chunks is None:
            return None
        logger.debug("tool decision_text %s → %d chunks", document_id, len(chunks))
        return DecisionText(
            document_id=document_id,
            case_number=detail.document.case_number,
            chunks=[
                DecisionTextChunk(
                    chunk_id=chunk.chunk_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    section=chunk.section,
                    appendix_label=chunk.appendix_label,
                )
                for chunk in chunks
            ],
        )

    async def decision_profile(
        self, *, document_id: uuid.UUID
    ) -> DecisionProfile | None:
        detail = await document_service.get_document_detail(self.session, document_id)
        if detail is None:
            return None
        logger.debug("tool decision_profile %s", document_id)
        return DecisionProfile(
            document_id=document_id,
            case_number=detail.document.case_number,
            decision_date=detail.document.decision_date,
            decision_outcome=detail.document.decision_outcome,
            category=detail.document.category,
            headline=detail.document.headline,
            summary=detail.document.summary,
            keywords=_names(detail.keywords),
            concepts=_names(detail.concepts),
            regulations=_names(detail.regulations),
            roles=_names(detail.roles),
            parishes=_names(detail.parishes),
            references_out=[
                edge.case_number
                for edge in detail.references_out
                if edge.case_number is not None
            ],
            references_in=[
                edge.case_number
                for edge in detail.references_in
                if edge.case_number is not None
            ],
        )

    async def tabular_query(self, *, question: str) -> agents.SqlAgentResult:
        result = await agents.run_sql_agent(
            agents.SqlAgentRequest(question=question),
            self.session,
            llm_provider=self.sql_llm_provider,
        )
        # The generated SQL previewed rather than logged whole: it is the one
        # thing that explains a wrong count, and the full text is in the turn's
        # `sql` event and its trace record either way.
        logger.debug(
            "tool tabular_query q=%s answered=%s rows=%d sql=%s",
            preview(question),
            result.answered,
            result.row_count,
            preview(result.sql) if result.sql else "-",
        )
        return result


def build_chat_toolset(
    session: AsyncSession,
    *,
    embedding_provider: EmbeddingProvider,
    search_settings: SearchSettings,
    sql_llm_provider: LLMProvider | None = None,
) -> ChatToolset:
    """One request's toolset, bound to that request's session."""
    return ApiChatToolset(
        session=session,
        embedding_provider=embedding_provider,
        search_settings=search_settings,
        sql_llm_provider=sql_llm_provider,
    )
