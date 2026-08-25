"""Endpoint-layer tests: status codes, validation and wiring.

Business logic is covered in the service tests; here the service is patched at
its import site in the route module so only the HTTP layer is under test.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.main import create_app
from api.services.document_service import (
    DocumentDetail,
    DocumentSections,
    DocumentSummary,
)
from api.services.search_service import SearchDiagnostics, SearchResponse
from shared.dtos.search import DocumentFacets


def _make_client() -> tuple[FastAPI, TestClient]:
    app = create_app()
    app.state.embedding_provider = MagicMock()
    app.state.structured_llm_provider = MagicMock()
    app.state.chat_llm_provider = MagicMock()
    app.state.storage = MagicMock()

    mock_db = AsyncMock(spec=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app)


def _empty_search_response(limit: int = 10) -> SearchResponse:
    return SearchResponse(
        items=[],
        total=0,
        limit=limit,
        offset=0,
        effective_queries=["utlämnande"],
        diagnostics=SearchDiagnostics(
            filter_applied=False,
            candidate_document_count=None,
            vector_hit_count=0,
            text_hit_counts={},
            fused_chunk_count=0,
            expanded=False,
            widened_to_appendices=False,
            vector_similarity_floor=0.78,
            top_vector_similarity=None,
        ),
    )


def _summary(document_id: uuid.UUID) -> DocumentSummary:
    return DocumentSummary(
        document_id=document_id,
        case_number="2024-0142",
        decision_number="12/2024",
        decision_date=date(2024, 5, 3),
        category="Utlämnande av handlingar",
        decision_outcome="avslår överklagandet",
        headline="Beslut om utlämnande",
        summary="Sammanfattning",
        source_url="https://example.com/beslut.pdf",
        source_published_at=datetime.now(),
        has_pdf=True,
    )


class TestSearchEndpoint:
    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def setup_method(self):
        self.app, self.client = _make_client()

    def test_valid_query_returns_200(self):
        with patch(
            "api.routes.search.search_documents",
            new=AsyncMock(return_value=_empty_search_response()),
        ):
            response = self.client.post("/api/search", json={"query": "utlämnande"})

        assert response.status_code == 200
        assert response.json()["effective_queries"] == ["utlämnande"]

    def test_empty_query_is_rejected_before_any_search(self):
        with patch("api.routes.search.search_documents") as mock_search:
            response = self.client.post("/api/search", json={"query": ""})

        assert response.status_code == 422
        mock_search.assert_not_called()

    def test_missing_query_is_rejected(self):
        response = self.client.post("/api/search", json={})
        assert response.status_code == 422

    def test_negative_offset_is_rejected(self):
        response = self.client.post(
            "/api/search", json={"query": "utlämnande", "offset": -1}
        )
        assert response.status_code == 422

    def test_unknown_filter_field_is_ignored_rather_than_rejected(self):
        with patch(
            "api.routes.search.search_documents",
            new=AsyncMock(return_value=_empty_search_response()),
        ):
            response = self.client.post(
                "/api/search",
                json={"query": "utlämnande", "filter": {"date_from": "2024-01-01"}},
            )
        assert response.status_code == 200

    def test_providers_from_app_state_are_passed_to_the_service(self):
        captured = {}

        async def fake_search(body, db, **kwargs):
            captured.update(kwargs)
            return _empty_search_response()

        with patch("api.routes.search.search_documents", new=fake_search):
            self.client.post("/api/search", json={"query": "utlämnande"})

        assert captured["embedding_provider"] is self.app.state.embedding_provider
        assert captured["llm_provider"] is self.app.state.structured_llm_provider


class TestFiltersEndpoint:
    def setup_method(self):
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def test_returns_the_facet_vocabulary(self):
        facets = DocumentFacets(
            categories=[],
            decision_outcomes=[],
            entity_types=[],
            keywords=[],
            earliest_decision_date=date(2019, 1, 1),
            latest_decision_date=date(2024, 12, 31),
            document_count=42,
        )
        with patch("api.routes.search.get_filters", new=AsyncMock(return_value=facets)):
            response = self.client.get("/api/filters")

        assert response.status_code == 200
        assert response.json()["document_count"] == 42


class TestDocumentEndpoints:
    def setup_method(self):
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def test_unknown_document_returns_404(self):
        with patch(
            "api.routes.documents.get_document_detail", new=AsyncMock(return_value=None)
        ):
            response = self.client.get(f"/api/documents/{uuid.uuid4()}")

        assert response.status_code == 404

    def test_malformed_document_id_returns_422(self):
        response = self.client.get("/api/documents/not-a-uuid")
        assert response.status_code == 422

    def test_detail_returns_200_with_traversal_targets(self):
        document_id = uuid.uuid4()
        detail = DocumentDetail(
            document=_summary(document_id),
            sections=DocumentSections(
                body_chunk_count=3, appendix_chunk_count=0, appendix_labels=[]
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
        with patch(
            "api.routes.documents.get_document_detail",
            new=AsyncMock(return_value=detail),
        ):
            response = self.client.get(f"/api/documents/{document_id}")

        assert response.status_code == 200
        assert response.json()["document"]["case_number"] == "2024-0142"

    def test_unknown_document_chunks_returns_404(self):
        with patch(
            "api.routes.documents.get_document_chunks", new=AsyncMock(return_value=None)
        ):
            response = self.client.get(f"/api/documents/{uuid.uuid4()}/chunks")

        assert response.status_code == 404

    def test_pdf_is_served_inline_as_application_pdf(self):
        document_id = uuid.uuid4()
        with patch(
            "api.routes.documents.get_document_pdf",
            new=AsyncMock(return_value=b"%PDF-1.7 body"),
        ):
            response = self.client.get(f"/api/documents/{document_id}/pdf")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"].startswith("inline")
        assert response.content == b"%PDF-1.7 body"

    def test_missing_pdf_returns_404(self):
        with patch(
            "api.routes.documents.get_document_pdf", new=AsyncMock(return_value=None)
        ):
            response = self.client.get(f"/api/documents/{uuid.uuid4()}/pdf")

        assert response.status_code == 404

    def test_list_clamps_limit_to_the_configured_maximum(self):
        captured = {}

        async def fake_list(db, document_filter, **kwargs):
            captured.update(kwargs)
            return MagicMock(items=[], total=0, limit=kwargs["limit"], offset=0)

        with patch("api.routes.documents.list_documents", new=fake_list):
            self.client.get("/api/documents", params={"limit": 100000})

        assert captured["limit"] == 50

    def test_list_rejects_a_zero_limit(self):
        response = self.client.get("/api/documents", params={"limit": 0})
        assert response.status_code == 422

    def test_list_filters_reach_the_service(self):
        captured = {}

        async def fake_list(db, document_filter, **kwargs):
            captured["filter"] = document_filter
            return MagicMock(items=[], total=0, limit=10, offset=0)

        with patch("api.routes.documents.list_documents", new=fake_list):
            self.client.get(
                "/api/documents",
                params={
                    "date_from": "2024-01-01",
                    "category": "Utlämnande",
                    "entity_name": ["kyrkorådet", "domkapitlet"],
                },
            )

        assert captured["filter"].date_from == date(2024, 1, 1)
        assert captured["filter"].category == "Utlämnande"
        assert captured["filter"].entity_names == ["kyrkorådet", "domkapitlet"]


class TestConceptEndpoints:
    def setup_method(self):
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def test_unknown_concept_returns_404(self):
        with patch(
            "api.routes.concepts.list_documents_for_concept",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.get(f"/api/concepts/{uuid.uuid4()}/documents")

        assert response.status_code == 404

    def test_invalid_entity_type_is_rejected(self):
        response = self.client.get(
            "/api/concepts", params={"entity_type": "not_a_type"}
        )
        assert response.status_code == 422

    def test_valid_entity_type_is_accepted(self):
        async def fake_list(db, **kwargs):
            return MagicMock(items=[], total=0, limit=10, offset=0)

        with patch("api.routes.concepts.list_concepts", new=fake_list):
            response = self.client.get(
                "/api/concepts", params={"entity_type": "legal_concept"}
            )

        assert response.status_code == 200

    def test_invalid_relevance_is_rejected(self):
        response = self.client.get(
            f"/api/concepts/{uuid.uuid4()}/documents",
            params={"relevance": "very_relevant"},
        )
        assert response.status_code == 422


class TestKeywordEndpoints:
    def setup_method(self):
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def test_unknown_keyword_returns_404(self):
        with patch(
            "api.routes.keywords.list_documents_for_keyword",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.get(f"/api/keywords/{uuid.uuid4()}/documents")

        assert response.status_code == 404

    def test_malformed_keyword_id_returns_422(self):
        response = self.client.get("/api/keywords/not-a-uuid/documents")
        assert response.status_code == 422

    def test_listing_returns_200(self):
        async def fake_list(db, **kwargs):
            return MagicMock(items=[], total=0, limit=10, offset=0)

        with patch("api.routes.keywords.list_keywords", new=fake_list):
            response = self.client.get("/api/keywords", params={"q": "jäv"})

        assert response.status_code == 200

    def test_keyword_filter_reaches_the_document_filter(self):
        captured = {}

        async def fake_list(db, document_filter, **kwargs):
            captured["filter"] = document_filter
            return MagicMock(items=[], total=0, limit=10, offset=0)

        with patch("api.routes.documents.list_documents", new=fake_list):
            self.client.get(
                "/api/documents",
                params={"keyword": ["jäv", "avvisning"]},
            )

        assert captured["filter"].keywords == ["jäv", "avvisning"]


class TestSearchAccessLog:
    """The search exit line, through the app's real middleware stack."""

    def setup_method(self):
        self.app, self.client = _make_client()

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def _exit_line(self, caplog) -> str:
        return [
            record.getMessage()
            for record in caplog.records
            if record.name == "api.access" and record.getMessage().startswith("←")
        ][0]

    def test_the_exit_line_reports_what_the_search_found(self, caplog):
        async def fake_search(*args, **kwargs):
            return _empty_search_response()

        with caplog.at_level(logging.INFO, logger="api.access"):
            with patch("api.routes.search.search_documents", new=fake_search):
                self.client.post("/api/search", json={"query": "utlämnande"})

        exit_line = self._exit_line(caplog)
        assert exit_line.startswith("← POST /api/search 200 in ")
        assert " hits=0" in exit_line
        assert " total=0" in exit_line
        assert " expanded=False" in exit_line

    def test_a_404_is_a_status_not_an_error(self, caplog):
        """`HTTPException` is handled inside this middleware, so no ERROR record."""

        async def fake_detail(db, document_id):
            return None

        with caplog.at_level(logging.INFO):
            with patch("api.routes.documents.get_document_detail", new=fake_detail):
                self.client.get(f"/api/documents/{uuid.uuid4()}")

        assert " 404 in " in self._exit_line(caplog)
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
