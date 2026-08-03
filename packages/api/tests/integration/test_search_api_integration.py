"""The retrieval endpoints end to end against real Postgres.

Only the embedding provider is faked — the vector arm needs a deterministic
vector, not a real model. Everything else is genuine: the filters reach SQL, the
graph joins run, and the PDF comes back out of a real storage backend.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.dependencies import get_db
from api.main import create_app
from shared.config import EMBEDDING_DIMENSION
from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate
from shared.dtos.document_reference import DocumentReferenceCreate
from shared.dtos.entity import EntityCreate
from shared.enums import ChunkSection, EntityRelevance, EntityType
from shared.repositories import chunk as chunk_repo
from shared.repositories import document as document_repo
from shared.repositories import document_entity as document_entity_repo
from shared.repositories import document_reference as document_reference_repo
from shared.repositories import entity as entity_repo
from shared.storage.keys import document_pdf_key
from shared.testing import to_async_url

_BODY_TEXT = (
    "Nämnden finner att handlingarna ska lämnas ut enligt offentlighetsprincipen."
)
_APPENDIX_TEXT = "Domkapitlet avslog begäran om utlämnande av handlingarna."
_PDF_BYTES = b"%PDF-1.7 fake body"


def _unit_vector(hot_index: int = 0) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    vector[hot_index] = 1.0
    return vector


@pytest.fixture
async def api_app(
    clean_database: None, test_database_url: str, local_storage
) -> AsyncGenerator[Any, None]:
    engine = create_async_engine(to_async_url(test_database_url))
    factory = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app()
    # The lifespan never runs here, so app.state is populated by hand.
    embedding_provider = MagicMock()
    embedding_provider.embed = AsyncMock(return_value=[_unit_vector()])
    app.state.embedding_provider = embedding_provider
    app.state.structured_llm_provider = MagicMock()
    app.state.chat_llm_provider = MagicMock()
    app.state.storage = local_storage

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    yield app
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def http_client(api_app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app), base_url="http://test"
    )


@pytest.fixture
async def seeded(session: AsyncSession, local_storage) -> dict[str, Any]:
    """One decision citing another, with concepts, an appendix and a stored PDF."""
    cited = await document_repo.create(
        session, DocumentCreate(source_url="https://example.com/cited.pdf")
    )
    await document_repo.update(
        session,
        cited.id,
        DocumentUpdate(
            raw_text=_BODY_TEXT,
            case_number="2020-0031",
            decision_number="3/2020",
            decision_date=date(2020, 2, 1),
            category="Utlämnande av handlingar",
            decision_outcome="bifaller överklagandet",
            summary="Äldre beslut om utlämnande.",
        ),
    )

    main = await document_repo.create(
        session,
        DocumentCreate(
            source_url="https://example.com/main.pdf",
            source_headline="Beslut om utlämnande av handlingar",
        ),
    )
    await document_repo.update(
        session,
        main.id,
        DocumentUpdate(
            raw_text=_BODY_TEXT,
            gcs_uri="stored",
            case_number="2024-0142",
            decision_number="12/2024",
            decision_date=date(2024, 5, 3),
            category="Utlämnande av handlingar",
            decision_outcome="avslår överklagandet",
            summary="Nämnden avslår överklagandet.",
        ),
    )

    await chunk_repo.bulk_create(
        session,
        [
            ChunkCreate(
                document_id=main.id,
                chunk_index=0,
                chunk_text=_BODY_TEXT,
                embedding=_unit_vector(),
                section=ChunkSection.BODY,
            ),
            ChunkCreate(
                document_id=main.id,
                chunk_index=1,
                chunk_text=_APPENDIX_TEXT,
                embedding=_unit_vector(1),
                section=ChunkSection.APPENDIX,
                appendix_label="Bilaga A",
            ),
        ],
    )

    concept = await entity_repo.upsert(
        session,
        EntityCreate(name="offentlighetsprincipen", type=EntityType.LEGAL_CONCEPT),
    )
    regulation = await entity_repo.upsert(
        session, EntityCreate(name="kyrkoordningen 54 kap", type=EntityType.REGULATION)
    )
    keyword = await entity_repo.upsert(
        session,
        EntityCreate(name="utlämnande av handlingar", type=EntityType.KEYWORD),
    )
    for entity in (concept, regulation, keyword):
        await document_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=main.id,
                entity_id=entity.id,
                relevance=EntityRelevance.PRIMARY,
            ),
        )
    await document_reference_repo.upsert(
        session,
        DocumentReferenceCreate(
            source_document_id=main.id,
            target_document_id=cited.id,
            reference_context="Jämför ÖN 2020-0031.",
        ),
    )
    await session.commit()

    local_storage.store(document_pdf_key(main.id), _PDF_BYTES)
    return {
        "main": main.id,
        "cited": cited.id,
        "concept": concept.id,
        "keyword": keyword.id,
    }


class TestSearchEndpoint:
    async def test_query_returns_the_document_with_its_matched_chunk(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.post(
                "/api/search", json={"query": "utlämnande av handlingar"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        hit = next(h for h in body["items"] if h["document_id"] == str(seeded["main"]))
        assert hit["case_number"] == "2024-0142"
        assert hit["decision_number"] == "12/2024"
        assert hit["summary"] == "Nämnden avslår överklagandet."
        assert hit["headline"] == "Beslut om utlämnande av handlingar"
        # Full chunk text, so the ranking can be judged.
        assert hit["chunks"][0]["text"] == _BODY_TEXT
        assert hit["chunks"][0]["section"] == "body"

    async def test_diagnostics_report_both_arms(self, http_client, seeded):
        async with http_client as client:
            response = await client.post(
                "/api/search", json={"query": "utlämnande av handlingar"}
            )

        diagnostics = response.json()["diagnostics"]
        assert diagnostics["filter_applied"] is False
        assert diagnostics["candidate_document_count"] is None
        assert diagnostics["vector_hit_count"] >= 1
        assert diagnostics["text_hit_counts"]["utlämnande av handlingar"] >= 1
        assert diagnostics["expanded"] is False

    async def test_date_filter_narrows_results(self, http_client, seeded):
        async with http_client as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "utlämnande av handlingar",
                    "filter": {"date_from": "2024-01-01"},
                },
            )

        body = response.json()
        assert body["diagnostics"]["filter_applied"] is True
        assert body["diagnostics"]["candidate_document_count"] == 1
        assert [h["document_id"] for h in body["items"]] == [str(seeded["main"])]

    async def test_filter_matching_nothing_returns_empty_not_a_wider_net(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "utlämnande av handlingar",
                    "filter": {"date_from": "2099-01-01"},
                },
            )

        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["diagnostics"]["candidate_document_count"] == 0

    async def test_supplied_queries_are_all_searched_and_echoed(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "utlämnande",
                    "queries": ["offentlighetsprincipen"],
                },
            )

        body = response.json()
        assert body["effective_queries"] == ["utlämnande", "offentlighetsprincipen"]
        assert set(body["diagnostics"]["text_hit_counts"]) == {
            "utlämnande",
            "offentlighetsprincipen",
        }

    async def test_appendices_are_excluded_unless_requested(self, http_client, seeded):
        async with http_client as client:
            default = await client.post("/api/search", json={"query": "domkapitlet"})
            widened = await client.post(
                "/api/search",
                json={"query": "domkapitlet", "include_appendices": True},
            )

        default_sections = {
            chunk["section"]
            for hit in default.json()["items"]
            for chunk in hit["chunks"]
        }
        widened_sections = {
            chunk["section"]
            for hit in widened.json()["items"]
            for chunk in hit["chunks"]
        }
        assert (
            "appendix" not in default_sections
            or default.json()["diagnostics"]["widened_to_appendices"]
        )
        assert "appendix" in widened_sections


class TestFiltersEndpoint:
    async def test_facets_describe_the_seeded_corpus(self, http_client, seeded):
        async with http_client as client:
            response = await client.get("/api/filters")

        body = response.json()
        assert body["document_count"] == 2
        assert body["earliest_decision_date"] == "2020-02-01"
        assert body["latest_decision_date"] == "2024-05-03"
        categories = {value["value"]: value["count"] for value in body["categories"]}
        assert categories["Utlämnande av handlingar"] == 2
        entity_types = {value["value"] for value in body["entity_types"]}
        assert {"legal_concept", "regulation"} <= entity_types


class TestDocumentEndpoints:
    async def test_browse_is_paged_and_newest_first(self, http_client, seeded):
        async with http_client as client:
            response = await client.get("/api/documents", params={"limit": 1})

        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 1
        assert body["items"][0]["document_id"] == str(seeded["main"])

    async def test_detail_carries_concepts_regulations_and_references(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.get(f"/api/documents/{seeded['main']}")

        body = response.json()
        assert body["document"]["case_number"] == "2024-0142"
        assert [c["name"] for c in body["concepts"]] == ["offentlighetsprincipen"]
        assert [r["name"] for r in body["regulations"]] == ["kyrkoordningen 54 kap"]
        assert body["references_out"][0]["document_id"] == str(seeded["cited"])
        assert body["references_out"][0]["case_number"] == "2020-0031"
        assert body["sections"]["body_chunk_count"] == 1
        assert body["sections"]["appendix_labels"] == ["Bilaga A"]

    async def test_traversal_from_a_reference_reaches_the_cited_decision(
        self, http_client, seeded
    ):
        """The loop the whole design exists for: hit -> detail -> cited decision."""
        async with http_client as client:
            detail = await client.get(f"/api/documents/{seeded['main']}")
            target_id = detail.json()["references_out"][0]["document_id"]
            cited = await client.get(f"/api/documents/{target_id}")

        assert cited.status_code == 200
        assert cited.json()["document"]["case_number"] == "2020-0031"
        # And back the other way.
        assert cited.json()["references_in"][0]["document_id"] == str(seeded["main"])

    async def test_unknown_document_is_404(self, http_client, seeded):
        async with http_client as client:
            response = await client.get(f"/api/documents/{uuid.uuid4()}")
        assert response.status_code == 404

    async def test_chunks_are_returned_in_order_without_embeddings(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.get(f"/api/documents/{seeded['main']}/chunks")

        body = response.json()
        assert [chunk["chunk_index"] for chunk in body] == [0, 1]
        assert "embedding" not in body[0]

    async def test_chunks_can_be_narrowed_to_a_section(self, http_client, seeded):
        async with http_client as client:
            response = await client.get(
                f"/api/documents/{seeded['main']}/chunks",
                params={"section": "appendix"},
            )

        body = response.json()
        assert len(body) == 1
        assert body[0]["appendix_label"] == "Bilaga A"

    async def test_pdf_is_served_inline_from_storage(self, http_client, seeded):
        async with http_client as client:
            response = await client.get(f"/api/documents/{seeded['main']}/pdf")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content == _PDF_BYTES

    async def test_document_without_a_pdf_is_404(self, http_client, seeded):
        async with http_client as client:
            response = await client.get(f"/api/documents/{seeded['cited']}/pdf")
        assert response.status_code == 404


class TestConceptEndpoints:
    async def test_concepts_are_listed_with_document_counts(self, http_client, seeded):
        async with http_client as client:
            response = await client.get(
                "/api/concepts", params={"entity_type": "legal_concept"}
            )

        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "offentlighetsprincipen"
        assert body["items"][0]["document_count"] == 1

    async def test_traversal_from_a_concept_reaches_its_decisions(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.get(f"/api/concepts/{seeded['concept']}/documents")

        body = response.json()
        assert [item["document_id"] for item in body["items"]] == [str(seeded["main"])]
        assert body["items"][0]["case_number"] == "2024-0142"
        assert body["items"][0]["relevance"] == "primary"

    async def test_unknown_concept_is_404(self, http_client, seeded):
        async with http_client as client:
            response = await client.get(f"/api/concepts/{uuid.uuid4()}/documents")
        assert response.status_code == 404


class TestKeywordEndpoints:
    async def test_keywords_are_listed_with_document_counts(self, http_client, seeded):
        async with http_client as client:
            response = await client.get("/api/keywords")

        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "utlämnande av handlingar"
        assert body["items"][0]["document_count"] == 1

    async def test_listing_excludes_inferred_concepts(self, http_client, seeded):
        # The seeded corpus also holds a legal concept and a regulation; neither
        # may leak into a keyword browse.
        async with http_client as client:
            response = await client.get("/api/keywords")

        names = [item["name"] for item in response.json()["items"]]
        assert "offentlighetsprincipen" not in names
        assert "kyrkoordningen 54 kap" not in names

    async def test_traversal_from_a_keyword_reaches_its_decisions(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.get(f"/api/keywords/{seeded['keyword']}/documents")

        body = response.json()
        assert [item["document_id"] for item in body["items"]] == [str(seeded["main"])]
        assert body["items"][0]["case_number"] == "2024-0142"

    async def test_unknown_keyword_is_404(self, http_client, seeded):
        async with http_client as client:
            response = await client.get(f"/api/keywords/{uuid.uuid4()}/documents")
        assert response.status_code == 404

    async def test_a_concept_id_is_404_on_the_keyword_route(self, http_client, seeded):
        async with http_client as client:
            response = await client.get(f"/api/keywords/{seeded['concept']}/documents")
        assert response.status_code == 404

    async def test_keyword_filter_narrows_the_document_browse(
        self, http_client, seeded
    ):
        async with http_client as client:
            hit = await client.get(
                "/api/documents", params={"keyword": "utlämnande av handlingar"}
            )
            miss = await client.get("/api/documents", params={"keyword": "jäv"})

        assert [item["document_id"] for item in hit.json()["items"]] == [
            str(seeded["main"])
        ]
        assert miss.json()["items"] == []

    async def test_filters_endpoint_reports_the_keyword_vocabulary(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.get("/api/filters")

        keywords = response.json()["keywords"]
        assert [(k["value"], k["count"]) for k in keywords] == [
            ("utlämnande av handlingar", 1)
        ]

    async def test_document_detail_separates_keywords_from_concepts(
        self, http_client, seeded
    ):
        async with http_client as client:
            response = await client.get(f"/api/documents/{seeded['main']}")

        body = response.json()
        assert [e["name"] for e in body["keywords"]] == ["utlämnande av handlingar"]
        assert [e["name"] for e in body["concepts"]] == ["offentlighetsprincipen"]
        assert body["other_entities"] == []
