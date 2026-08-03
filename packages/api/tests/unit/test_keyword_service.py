from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

from api.services.keyword_service import list_documents_for_keyword, list_keywords
from shared.dtos.document_entity import EntityDocumentRef
from shared.dtos.entity import EntityRead, EntityWithCount
from shared.enums import EntityRelevance, EntityType


def _keyword_with_count(name: str, count: int) -> EntityWithCount:
    return EntityWithCount(
        id=uuid.uuid4(),
        name=name,
        type=EntityType.KEYWORD,
        document_count=count,
    )


def _entity_read(entity_id: uuid.UUID, entity_type: EntityType) -> EntityRead:
    return EntityRead(
        id=entity_id,
        name="utlämnande av handlingar",
        type=entity_type,
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


class TestListKeywords:
    async def test_returns_a_page_with_document_counts(self):
        with patch("api.services.keyword_service.entity_repo") as mock_entity:
            mock_entity.list_entities = AsyncMock(
                return_value=[_keyword_with_count("utlämnande av handlingar", 12)]
            )
            mock_entity.count_entities = AsyncMock(return_value=1)

            page = await list_keywords(AsyncMock(), limit=10)

        assert page.total == 1
        assert page.items[0].document_count == 12

    async def test_the_entity_type_is_pinned_to_keyword(self):
        # The whole point of a separate endpoint: a caller cannot widen it into a
        # browse over inferred concepts.
        with patch("api.services.keyword_service.entity_repo") as mock_entity:
            mock_entity.list_entities = AsyncMock(return_value=[])
            mock_entity.count_entities = AsyncMock(return_value=0)

            await list_keywords(AsyncMock(), name_query="jäv", limit=10)

        assert mock_entity.list_entities.call_args.kwargs["entity_type"] == (
            EntityType.KEYWORD
        )
        assert mock_entity.count_entities.call_args.kwargs["entity_type"] == (
            EntityType.KEYWORD
        )


class TestListDocumentsForKeyword:
    async def test_returns_the_decisions_carrying_the_keyword(self):
        keyword_id = uuid.uuid4()
        with (
            patch("api.services.keyword_service.entity_repo") as mock_entity,
            patch("api.services.keyword_service.document_entity_repo") as mock_link,
        ):
            mock_entity.get_by_id = AsyncMock(
                return_value=_entity_read(keyword_id, EntityType.KEYWORD)
            )
            mock_link.list_documents_for_entity = AsyncMock(
                return_value=[_document_ref()]
            )
            mock_link.count_documents_for_entity = AsyncMock(return_value=1)

            page = await list_documents_for_keyword(AsyncMock(), keyword_id, limit=10)

        assert page is not None
        assert page.total == 1

    async def test_unknown_id_returns_none(self):
        with patch("api.services.keyword_service.entity_repo") as mock_entity:
            mock_entity.get_by_id = AsyncMock(return_value=None)

            page = await list_documents_for_keyword(AsyncMock(), uuid.uuid4(), limit=10)

        assert page is None

    async def test_an_entity_of_another_type_returns_none(self):
        # Every keyword is an entity but not every entity is a keyword; serving a
        # legal concept here would make the two indistinguishable to a caller.
        concept_id = uuid.uuid4()
        with (
            patch("api.services.keyword_service.entity_repo") as mock_entity,
            patch("api.services.keyword_service.document_entity_repo") as mock_link,
        ):
            mock_entity.get_by_id = AsyncMock(
                return_value=_entity_read(concept_id, EntityType.LEGAL_CONCEPT)
            )
            mock_link.list_documents_for_entity = AsyncMock()

            page = await list_documents_for_keyword(AsyncMock(), concept_id, limit=10)

        assert page is None
        mock_link.list_documents_for_entity.assert_not_called()
