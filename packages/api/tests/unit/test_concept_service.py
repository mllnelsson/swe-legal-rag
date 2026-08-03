from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.concept_service import list_concepts, list_documents_for_concept
from shared.dtos.document_entity import EntityDocumentRef
from shared.dtos.entity import EntityRead, EntityWithCount
from shared.enums import EntityRelevance, EntityType


def _entity_with_count(name: str, count: int) -> EntityWithCount:
    return EntityWithCount(
        id=uuid.uuid4(),
        name=name,
        type=EntityType.LEGAL_CONCEPT,
        document_count=count,
    )


def _entity_read(entity_id: uuid.UUID) -> EntityRead:
    return EntityRead(
        id=entity_id,
        name="offentlighetsprincipen",
        type=EntityType.LEGAL_CONCEPT,
        created_at=datetime.now(),
    )


def _document_ref() -> EntityDocumentRef:
    return EntityDocumentRef(
        document_id=uuid.uuid4(),
        case_number="2024-0142",
        decision_number="12/2024",
        decision_date=date(2024, 5, 3),
        headline="Beslut om utlämnande",
        category="Utlämnande av handlingar",
        decision_outcome="avslår överklagandet",
        relevance=EntityRelevance.PRIMARY,
    )


class TestListConcepts:
    async def test_returns_a_page_with_document_counts(self):
        with patch("api.services.concept_service.entity_repo") as mock_entity:
            mock_entity.list_entities = AsyncMock(
                return_value=[_entity_with_count("offentlighetsprincipen", 12)]
            )
            mock_entity.count_entities = AsyncMock(return_value=1)

            page = await list_concepts(MagicMock(), limit=10)

        assert page.total == 1
        assert page.items[0].document_count == 12

    async def test_type_and_name_filters_reach_the_repository(self):
        with patch("api.services.concept_service.entity_repo") as mock_entity:
            mock_entity.list_entities = AsyncMock(return_value=[])
            mock_entity.count_entities = AsyncMock(return_value=0)

            await list_concepts(
                MagicMock(),
                entity_type=EntityType.REGULATION,
                name_query="kyrkoordning",
                limit=5,
                offset=10,
            )

        kwargs = mock_entity.list_entities.await_args_list[0].kwargs
        assert kwargs["entity_type"] == EntityType.REGULATION
        assert kwargs["name_query"] == "kyrkoordning"
        assert kwargs["limit"] == 5
        assert kwargs["offset"] == 10


class TestListDocumentsForConcept:
    async def test_unknown_entity_returns_none(self):
        """Distinguishing an unknown concept from an unused one is what makes 404
        the right answer rather than an empty page."""
        with patch("api.services.concept_service.entity_repo") as mock_entity:
            mock_entity.get_by_id = AsyncMock(return_value=None)
            result = await list_documents_for_concept(
                MagicMock(), uuid.uuid4(), limit=10
            )
        assert result is None

    async def test_known_entity_with_no_documents_returns_an_empty_page(self):
        entity_id = uuid.uuid4()
        with (
            patch("api.services.concept_service.entity_repo") as mock_entity,
            patch("api.services.concept_service.document_entity_repo") as mock_de,
        ):
            mock_entity.get_by_id = AsyncMock(return_value=_entity_read(entity_id))
            mock_de.list_documents_for_entity = AsyncMock(return_value=[])
            mock_de.count_documents_for_entity = AsyncMock(return_value=0)

            page = await list_documents_for_concept(MagicMock(), entity_id, limit=10)

        assert page is not None
        assert page.items == []
        assert page.total == 0

    async def test_documents_are_returned_with_identity_for_linking(self):
        entity_id = uuid.uuid4()
        with (
            patch("api.services.concept_service.entity_repo") as mock_entity,
            patch("api.services.concept_service.document_entity_repo") as mock_de,
        ):
            mock_entity.get_by_id = AsyncMock(return_value=_entity_read(entity_id))
            mock_de.list_documents_for_entity = AsyncMock(
                return_value=[_document_ref()]
            )
            mock_de.count_documents_for_entity = AsyncMock(return_value=1)

            page = await list_documents_for_concept(MagicMock(), entity_id, limit=10)

        assert page is not None
        assert page.items[0].case_number == "2024-0142"
        assert page.items[0].decision_number == "12/2024"

    async def test_relevance_filter_reaches_both_repository_calls(self):
        entity_id = uuid.uuid4()
        with (
            patch("api.services.concept_service.entity_repo") as mock_entity,
            patch("api.services.concept_service.document_entity_repo") as mock_de,
        ):
            mock_entity.get_by_id = AsyncMock(return_value=_entity_read(entity_id))
            mock_de.list_documents_for_entity = AsyncMock(return_value=[])
            mock_de.count_documents_for_entity = AsyncMock(return_value=0)

            await list_documents_for_concept(
                MagicMock(), entity_id, relevance=EntityRelevance.PRIMARY, limit=10
            )

        assert (
            mock_de.list_documents_for_entity.await_args_list[0].kwargs["relevance"]
            == EntityRelevance.PRIMARY
        )
        assert (
            mock_de.count_documents_for_entity.await_args_list[0].kwargs["relevance"]
            == EntityRelevance.PRIMARY
        )
