from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import RetrievalSettings
from api.services.query_planner import QueryPlan
from api.services.retriever import RetrievedChunk, retrieve
from shared.config import EMBEDDING_DIMENSION
from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate
from shared.dtos.document_reference import DocumentReferenceCreate
from shared.dtos.entity import EntityCreate
from shared.dtos.search import DocumentFilter
from shared.repositories.chunk import ChunkRepository
from shared.repositories.document import DocumentRepository
from shared.repositories.document_entity import DocumentEntityRepository
from shared.repositories.document_reference import DocumentReferenceRepository
from shared.repositories.entity import EntityRepository

pytestmark = pytest.mark.integration

_SWEDISH_TEXT = "Kyrkorådet beslutade att bifalla överklagandet."


def _unit_vector(hot_index: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIMENSION
    v[hot_index] = 1.0
    return v


def _settings(
    retrieval_top_k: int = 8,
    retrieval_search_limit: int = 20,
    retrieval_rerank_enabled: bool = False,
) -> RetrievalSettings:
    return RetrievalSettings(
        retrieval_top_k=retrieval_top_k,
        retrieval_search_limit=retrieval_search_limit,
        retrieval_rerank_enabled=retrieval_rerank_enabled,
    )


def _make_embedding_provider(embedding: list[float] | None = None) -> MagicMock:
    provider = MagicMock()
    provider.embed = AsyncMock(return_value=[embedding or _unit_vector(0)])
    return provider


async def _seed_document(
    document_repo: DocumentRepository,
    session: AsyncSession,
    *,
    source_url: str,
    case_number: str | None = None,
    decision_date: date | None = None,
    decision_outcome: str | None = None,
    category: str | None = None,
    raw_text: str = _SWEDISH_TEXT,
) -> uuid.UUID:
    doc = await document_repo.create(DocumentCreate(source_url=source_url))
    await document_repo.update(
        doc.id,
        DocumentUpdate(
            raw_text=raw_text,
            case_number=case_number,
            decision_date=decision_date,
            decision_outcome=decision_outcome,
            category=category,
        ),
    )
    await session.commit()
    return doc.id


async def _seed_chunk(
    chunk_repo: ChunkRepository,
    session: AsyncSession,
    document_id: uuid.UUID,
    chunk_text: str = _SWEDISH_TEXT,
    embedding: list[float] | None = None,
    chunk_index: int = 0,
) -> uuid.UUID:
    if embedding is None:
        embedding = _unit_vector(0)
    chunks = await chunk_repo.bulk_create([
        ChunkCreate(
            document_id=document_id,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            embedding=embedding,
        )
    ])
    await session.commit()
    return chunks[0].id


class TestRetrievePipelineIntegration:
    async def test_retrieve_with_empty_filter_returns_top_chunks(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        session: AsyncSession,
    ) -> None:
        doc_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/r1.pdf",
            case_number="2023/001",
            decision_date=date(2023, 3, 1),
            category="Kyrkogård",
        )
        await _seed_chunk(chunk_repo, session, doc_id, embedding=_unit_vector(0))

        plan = QueryPlan(semantic_query="kyrkorätt", filter=DocumentFilter())
        provider = _make_embedding_provider(_unit_vector(0))

        results = await retrieve(plan, session, embedding_provider=provider, settings=_settings())

        assert len(results) >= 1
        assert isinstance(results[0], RetrievedChunk)
        assert results[0].case_number == "2023/001"
        assert results[0].category == "Kyrkogård"

    async def test_retrieve_metadata_filter_narrows_candidates(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        session: AsyncSession,
    ) -> None:
        match_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/r2.pdf",
            case_number="2023/002",
            category="Kyrkogårdsförvaltning",
        )
        no_match_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/r3.pdf",
            case_number="2023/003",
            category="Ekonomi",
        )
        await _seed_chunk(chunk_repo, session, match_id, embedding=_unit_vector(0))
        await _seed_chunk(chunk_repo, session, no_match_id, embedding=_unit_vector(0))

        plan = QueryPlan(
            semantic_query="kyrkogård",
            filter=DocumentFilter(category="Kyrkogård"),
        )
        provider = _make_embedding_provider(_unit_vector(0))

        results = await retrieve(plan, session, embedding_provider=provider, settings=_settings())

        doc_ids = {r.document_id for r in results}
        assert match_id in doc_ids
        assert no_match_id not in doc_ids

    async def test_retrieve_falls_back_to_unfiltered_on_empty_candidates(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        session: AsyncSession,
    ) -> None:
        doc_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/r4.pdf",
            case_number="2023/004",
            category="Ekonomi",
        )
        await _seed_chunk(chunk_repo, session, doc_id, embedding=_unit_vector(0))

        # Filter for a category that does not exist → candidates empty → fallback to unfiltered
        plan = QueryPlan(
            semantic_query="kyrkorätt",
            filter=DocumentFilter(category="XYZNonExistent"),
        )
        provider = _make_embedding_provider(_unit_vector(0))

        results = await retrieve(plan, session, embedding_provider=provider, settings=_settings())

        # Fallback: should still return the only available document
        assert len(results) >= 1
        assert any(r.document_id == doc_id for r in results)

    async def test_retrieve_entity_filter_narrows_candidates(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        entity_repo: EntityRepository,
        doc_entity_repo: DocumentEntityRepository,
        session: AsyncSession,
    ) -> None:
        match_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/r5.pdf",
            case_number="2023/005",
        )
        no_match_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/r6.pdf",
            case_number="2023/006",
        )
        await _seed_chunk(chunk_repo, session, match_id, embedding=_unit_vector(0))
        await _seed_chunk(chunk_repo, session, no_match_id, embedding=_unit_vector(0))

        entity = await entity_repo.upsert(EntityCreate(name="kyrkorådet", type="role"))
        await doc_entity_repo.upsert(
            DocumentEntityCreate(document_id=match_id, entity_id=entity.id, relevance="primary")
        )
        await session.commit()

        plan = QueryPlan(
            semantic_query="kyrkorätt",
            filter=DocumentFilter(entity_names=["kyrkorådet"]),
        )
        provider = _make_embedding_provider(_unit_vector(0))

        results = await retrieve(plan, session, embedding_provider=provider, settings=_settings())

        doc_ids = {r.document_id for r in results}
        assert match_id in doc_ids
        assert no_match_id not in doc_ids

    async def test_retrieve_reference_traversal_includes_related_document(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        doc_ref_repo: DocumentReferenceRepository,
        session: AsyncSession,
    ) -> None:
        # doc1 cites doc2; searching for doc1's case number should include doc2
        doc1_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/r7.pdf",
            case_number="2020/010",
        )
        doc2_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/r8.pdf",
            case_number="2021/010",
        )
        await _seed_chunk(chunk_repo, session, doc1_id, embedding=_unit_vector(0), chunk_index=0)
        await _seed_chunk(chunk_repo, session, doc2_id, embedding=_unit_vector(0), chunk_index=0)

        await doc_ref_repo.upsert(
            DocumentReferenceCreate(source_document_id=doc1_id, target_document_id=doc2_id)
        )
        await session.commit()

        plan = QueryPlan(
            semantic_query="kyrkorätt",
            filter=DocumentFilter(references_case_number="2020/010"),
        )
        provider = _make_embedding_provider(_unit_vector(0))

        results = await retrieve(plan, session, embedding_provider=provider, settings=_settings())

        doc_ids = {r.document_id for r in results}
        assert doc2_id in doc_ids

    async def test_retrieve_respects_top_k_limit(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        session: AsyncSession,
    ) -> None:
        # Seed 5 documents with 1 chunk each
        for i in range(5):
            doc_id = await _seed_document(
                document_repo, session,
                source_url=f"https://a.com/topk{i}.pdf",
            )
            await _seed_chunk(
                chunk_repo, session, doc_id,
                embedding=_unit_vector(i % EMBEDDING_DIMENSION),
            )

        plan = QueryPlan(semantic_query="kyrkorätt", filter=DocumentFilter())
        provider = _make_embedding_provider(_unit_vector(0))

        results = await retrieve(
            plan, session, embedding_provider=provider,
            settings=_settings(retrieval_top_k=3),
        )

        assert len(results) <= 3

    async def test_retrieve_result_has_document_metadata(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        session: AsyncSession,
    ) -> None:
        doc_id = await _seed_document(
            document_repo, session,
            source_url="https://a.com/meta1.pdf",
            case_number="2023/099",
            decision_date=date(2023, 9, 15),
            decision_outcome="bifaller",
            category="Kyrkogård",
        )
        await _seed_chunk(chunk_repo, session, doc_id, embedding=_unit_vector(0))

        plan = QueryPlan(semantic_query="kyrkorätt", filter=DocumentFilter())
        provider = _make_embedding_provider(_unit_vector(0))

        results = await retrieve(plan, session, embedding_provider=provider, settings=_settings())

        assert len(results) >= 1
        chunk = next(r for r in results if r.document_id == doc_id)
        assert chunk.case_number == "2023/099"
        assert chunk.decision_date == date(2023, 9, 15)
        assert chunk.decision_outcome == "bifaller"
        assert chunk.category == "Kyrkogård"
