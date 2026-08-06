from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import EMBEDDING_DIMENSION
from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate
from shared.dtos.document_reference import DocumentReferenceCreate
from shared.dtos.entity import EntityCreate
from shared.dtos.search import DocumentFilter
from shared.search.rrf import rrf_fuse

_SWEDISH_TEXT = "Kyrkorådet beslutade att bifalla överklagandet."


def _unit_vector(hot_index: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIMENSION
    v[hot_index] = 1.0
    return v


async def _seed_document(
    document_repo,
    session: AsyncSession,
    *,
    source_url: str = "https://example.com/doc.pdf",
    case_number: str | None = None,
    decision_date: date | None = None,
    decision_outcome: str | None = None,
    category: str | None = None,
    raw_text: str = _SWEDISH_TEXT,
) -> uuid.UUID:
    doc = await document_repo.create(session, DocumentCreate(source_url=source_url))
    await document_repo.update(
        session,
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
    chunk_repo,
    session: AsyncSession,
    document_id: uuid.UUID,
    chunk_text: str = _SWEDISH_TEXT,
    embedding: list[float] | None = None,
    chunk_index: int = 0,
) -> uuid.UUID:
    if embedding is None:
        embedding = [0.1] * EMBEDDING_DIMENSION
    chunk = await chunk_repo.bulk_create(
        session,
        [
            ChunkCreate(
                document_id=document_id,
                chunk_index=chunk_index,
                chunk_text=chunk_text,
                embedding=embedding,
            )
        ],
    )
    await session.commit()
    return chunk[0].id


class TestSearchRepositoryMetadataFiltering:
    async def test_empty_filter_returns_docs_with_raw_text(
        self,
        document_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        doc1_id = await _seed_document(
            document_repo, session, source_url="https://a.com/1.pdf"
        )
        doc2_id = await _seed_document(
            document_repo, session, source_url="https://a.com/2.pdf"
        )

        results = await search_repo.find_candidate_documents(session, DocumentFilter())

        assert doc1_id in results
        assert doc2_id in results

    async def test_date_from_excludes_earlier_documents(
        self,
        document_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        old_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/old.pdf",
            decision_date=date(2020, 6, 1),
        )
        new_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/new.pdf",
            decision_date=date(2023, 6, 1),
        )

        results = await search_repo.find_candidate_documents(
            session, DocumentFilter(date_from=date(2022, 1, 1))
        )

        assert new_id in results
        assert old_id not in results

    async def test_date_to_excludes_later_documents(
        self,
        document_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        old_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/old2.pdf",
            decision_date=date(2020, 6, 1),
        )
        new_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/new2.pdf",
            decision_date=date(2023, 6, 1),
        )

        results = await search_repo.find_candidate_documents(
            session, DocumentFilter(date_to=date(2021, 12, 31))
        )

        assert old_id in results
        assert new_id not in results

    async def test_category_ilike_matches_partial_name(
        self,
        document_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        match_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/cat1.pdf",
            category="Kyrkogårdsförvaltning",
        )
        no_match_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/cat2.pdf",
            category="Ekonomi",
        )

        results = await search_repo.find_candidate_documents(
            session, DocumentFilter(category="kyrkogård")
        )

        assert match_id in results
        assert no_match_id not in results


class TestSearchRepositoryEntityFiltering:
    async def test_entity_name_filter_returns_matching_document(
        self,
        document_repo,
        entity_repo,
        doc_entity_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        match_id = await _seed_document(
            document_repo, session, source_url="https://a.com/ent1.pdf"
        )
        no_match_id = await _seed_document(
            document_repo, session, source_url="https://a.com/ent2.pdf"
        )

        entity = await entity_repo.upsert(
            session, EntityCreate(name="kyrkorådet", type="role")
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=match_id, entity_id=entity.id, relevance="primary"
            ),
        )
        await session.commit()

        results = await search_repo.find_candidate_documents(
            session, DocumentFilter(entity_names=["kyrkorådet"])
        )

        assert match_id in results
        assert no_match_id not in results

    async def test_entity_name_ilike_partial_match(
        self,
        document_repo,
        entity_repo,
        doc_entity_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        match_id = await _seed_document(
            document_repo, session, source_url="https://a.com/ent3.pdf"
        )

        entity = await entity_repo.upsert(
            session, EntityCreate(name="Skattkärrens församling", type="parish")
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=match_id, entity_id=entity.id, relevance="mentioned"
            ),
        )
        await session.commit()

        results = await search_repo.find_candidate_documents(
            session, DocumentFilter(entity_names=["skattkärren"])
        )

        assert match_id in results


class TestSearchRepositoryReferenceTraversal:
    async def test_reference_traversal_returns_cited_document(
        self,
        document_repo,
        doc_ref_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        # doc1 cites doc2 (source=doc1, target=doc2)
        doc1_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/ref1.pdf",
            case_number="2020/001",
        )
        doc2_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/ref2.pdf",
            case_number="2021/001",
        )
        await doc_ref_repo.upsert(
            session,
            DocumentReferenceCreate(
                source_document_id=doc1_id, target_document_id=doc2_id
            ),
        )
        await session.commit()

        # Searching for "2020/001" (doc1's case) → related_as_source gives doc2
        results = await search_repo.find_candidate_documents(
            session, DocumentFilter(references_case_number="2020/001")
        )

        assert doc2_id in results

    async def test_reference_traversal_returns_citing_document(
        self,
        document_repo,
        doc_ref_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        # doc1 cites doc2 (source=doc1, target=doc2)
        doc1_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/ref3.pdf",
            case_number="2020/002",
        )
        doc2_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/ref4.pdf",
            case_number="2021/002",
        )
        await doc_ref_repo.upsert(
            session,
            DocumentReferenceCreate(
                source_document_id=doc1_id, target_document_id=doc2_id
            ),
        )
        await session.commit()

        # Searching for "2021/002" (doc2's case) → related_as_target gives doc1
        results = await search_repo.find_candidate_documents(
            session, DocumentFilter(references_case_number="2021/002")
        )

        assert doc1_id in results

    async def test_reference_traversal_both_directions(
        self,
        document_repo,
        doc_ref_repo,
        search_repo,
        session: AsyncSession,
    ) -> None:
        # doc1 cites pivot; pivot cites doc2
        doc1_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/ref5.pdf",
            case_number="2019/001",
        )
        pivot_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/ref6.pdf",
            case_number="2020/003",
        )
        doc2_id = await _seed_document(
            document_repo,
            session,
            source_url="https://a.com/ref7.pdf",
            case_number="2021/003",
        )
        await doc_ref_repo.upsert(
            session,
            DocumentReferenceCreate(
                source_document_id=doc1_id, target_document_id=pivot_id
            ),
        )
        await doc_ref_repo.upsert(
            session,
            DocumentReferenceCreate(
                source_document_id=pivot_id, target_document_id=doc2_id
            ),
        )
        await session.commit()

        # Pivot is cited by doc1 AND cites doc2 → both should appear
        results = await search_repo.find_candidate_documents(
            session, DocumentFilter(references_case_number="2020/003")
        )

        assert doc1_id in results
        assert doc2_id in results


class TestChunkRepositoryVectorSearch:
    async def test_vector_search_orders_by_cosine_distance(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        # chunk_a: unit vector in dim 0 — closest to query
        # chunk_b: unit vector in dim 1 — orthogonal to query
        # chunk_c: unit vector opposite to dim 0 — farthest from query
        doc_id = await _seed_document(
            document_repo, session, source_url="https://a.com/vs.pdf"
        )
        chunk_a_id = await _seed_chunk(
            chunk_repo, session, doc_id, embedding=_unit_vector(0), chunk_index=0
        )
        chunk_b_id = await _seed_chunk(
            chunk_repo, session, doc_id, embedding=_unit_vector(1), chunk_index=1
        )
        neg_vec = [0.0] * EMBEDDING_DIMENSION
        neg_vec[0] = -1.0
        chunk_c_id = await _seed_chunk(
            chunk_repo, session, doc_id, embedding=neg_vec, chunk_index=2
        )

        query_vec = _unit_vector(0)
        results = await chunk_repo.vector_search(
            session, embedding=query_vec, document_ids=None, limit=10
        )

        result_ids = [r.id for r in results]
        assert result_ids[0] == chunk_a_id
        # chunk_b (distance 1.0) before chunk_c (distance 2.0)
        assert result_ids.index(chunk_b_id) < result_ids.index(chunk_c_id)

    async def test_vector_search_filtered_to_document_ids(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        doc1_id = await _seed_document(
            document_repo, session, source_url="https://a.com/vs2.pdf"
        )
        doc2_id = await _seed_document(
            document_repo, session, source_url="https://a.com/vs3.pdf"
        )
        await _seed_chunk(chunk_repo, session, doc1_id, embedding=_unit_vector(0))
        chunk2_id = await _seed_chunk(
            chunk_repo, session, doc2_id, embedding=_unit_vector(0)
        )

        # Only search in doc2 — doc1 chunk should not appear
        results = await chunk_repo.vector_search(
            session,
            embedding=_unit_vector(0),
            document_ids=[doc2_id],
            limit=10,
        )

        result_ids = [r.id for r in results]
        assert chunk2_id in result_ids
        assert all(r.document_id == doc2_id for r in results)

    async def test_vector_search_reports_similarity_not_distance(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        """`score` runs the same direction on both arms: higher is a better match."""
        doc_id = await _seed_document(
            document_repo, session, source_url="https://a.com/vs4.pdf"
        )
        await _seed_chunk(
            chunk_repo, session, doc_id, embedding=_unit_vector(0), chunk_index=0
        )
        await _seed_chunk(
            chunk_repo, session, doc_id, embedding=_unit_vector(1), chunk_index=1
        )

        results = await chunk_repo.vector_search(
            session, embedding=_unit_vector(0), document_ids=None, limit=10
        )

        # Identical vector: similarity 1.0, not distance 0.0. Orthogonal: 0.0.
        assert results[0].score == pytest.approx(1.0)
        assert results[1].score == pytest.approx(0.0)

    async def test_min_similarity_drops_neighbours_below_the_floor(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        """Nearest is not the same as near.

        Without the floor this scan returns both chunks for any query at all,
        which is what made an empty search result unreachable.
        """
        doc_id = await _seed_document(
            document_repo, session, source_url="https://a.com/vs5.pdf"
        )
        close_id = await _seed_chunk(
            chunk_repo, session, doc_id, embedding=_unit_vector(0), chunk_index=0
        )
        await _seed_chunk(
            chunk_repo, session, doc_id, embedding=_unit_vector(1), chunk_index=1
        )

        floored = await chunk_repo.vector_search(
            session,
            embedding=_unit_vector(0),
            document_ids=None,
            limit=10,
            min_similarity=0.5,
        )

        assert [r.id for r in floored] == [close_id]

    async def test_a_floor_nothing_reaches_returns_nothing(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        doc_id = await _seed_document(
            document_repo, session, source_url="https://a.com/vs6.pdf"
        )
        await _seed_chunk(chunk_repo, session, doc_id, embedding=_unit_vector(1))

        results = await chunk_repo.vector_search(
            session,
            embedding=_unit_vector(0),
            document_ids=None,
            limit=10,
            min_similarity=0.5,
        )

        assert results == []


class TestChunkRepositoryTextSearch:
    async def test_text_search_matches_swedish_stem(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        doc_id = await _seed_document(
            document_repo, session, source_url="https://a.com/ts1.pdf"
        )
        # "beslutade" is the past tense of "besluta"; Swedish tsvector stems it to "beslut"
        await _seed_chunk(
            chunk_repo,
            session,
            doc_id,
            chunk_text="Kyrkorådet beslutade att bifalla överklagandet.",
        )

        # Querying with the stem — websearch_to_tsquery('swedish', 'beslut') should match
        results = await chunk_repo.text_search(
            session, query="beslut", document_ids=None, limit=10
        )

        assert len(results) >= 1
        assert any(
            "beslutade" in r.chunk_text or "beslut" in r.chunk_text for r in results
        )

    async def test_text_search_inflected_form_matches(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        doc_id = await _seed_document(
            document_repo, session, source_url="https://a.com/ts2.pdf"
        )
        # "överklaganden" (plural) and "överklagandet" (definite) share the stem "överklag"
        await _seed_chunk(
            chunk_repo,
            session,
            doc_id,
            chunk_text="Nämnden avslår överklagandet från kyrkoherden.",
        )

        # Query with a different inflection of the same root
        results = await chunk_repo.text_search(
            session, query="överklaganden", document_ids=None, limit=10
        )

        assert len(results) >= 1

    async def test_text_search_no_match_returns_empty(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        doc_id = await _seed_document(
            document_repo, session, source_url="https://a.com/ts3.pdf"
        )
        await _seed_chunk(
            chunk_repo,
            session,
            doc_id,
            chunk_text="Kyrkorådet beslutade att bifalla överklagandet.",
        )

        results = await chunk_repo.text_search(
            session, query="skattedeklaration", document_ids=None, limit=10
        )

        assert results == []


class TestRrfFuseOnRealSearchResults:
    async def test_rrf_fuse_promotes_chunk_in_both_lists(
        self,
        document_repo,
        chunk_repo,
        session: AsyncSession,
    ) -> None:
        doc_id = await _seed_document(
            document_repo, session, source_url="https://a.com/rrf1.pdf"
        )
        # chunk_a: matches both vector and text search
        chunk_a_id = await _seed_chunk(
            chunk_repo,
            session,
            doc_id,
            chunk_text="Kyrkorådet beslutade att bifalla överklagandet.",
            embedding=_unit_vector(0),
            chunk_index=0,
        )
        # chunk_b: only matches vector search
        chunk_b_id = await _seed_chunk(
            chunk_repo,
            session,
            doc_id,
            chunk_text="Inget relevant innehåll här.",
            embedding=_unit_vector(0),
            chunk_index=1,
        )

        query_vec = _unit_vector(0)
        vector_results = await chunk_repo.vector_search(
            session, embedding=query_vec, document_ids=None, limit=10
        )
        text_results = await chunk_repo.text_search(
            session, query="beslut", document_ids=None, limit=10
        )

        fused = rrf_fuse(
            [
                [r.id for r in vector_results],
                [r.id for r in text_results],
            ]
        )

        # chunk_a appears in both lists → higher RRF score → should rank first or equal
        assert chunk_a_id in fused
        assert chunk_b_id in fused
        assert fused.index(chunk_a_id) <= fused.index(chunk_b_id)
