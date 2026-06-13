from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from shared.dtos.entity import EntityRead
from worker_extract.models import EntityType, ExtractedEntity, Relevance
from worker_extract.services.entity_service import (
    _deduplicate_entities,
    normalize_entity_name,
    persist_entities,
)


def _entity(name: str, etype: EntityType = EntityType.ROLE, relevance: Relevance = Relevance.MENTIONED) -> ExtractedEntity:
    return ExtractedEntity(name=name, type=etype, relevance=relevance)


def _entity_read(name: str) -> EntityRead:
    return EntityRead(id=uuid.uuid4(), name=name, type="role", created_at=datetime.now(tz=timezone.utc))


class TestNormalizeEntityName:
    def test_entity_persist_normalize_lowercases(self) -> None:
        assert normalize_entity_name("Kyrkoherde") == "kyrkoherde"

    def test_entity_persist_normalize_strips_whitespace(self) -> None:
        assert normalize_entity_name("  kyrkoherde  ") == "kyrkoherde"

    def test_entity_persist_normalize_collapses_internal_whitespace(self) -> None:
        assert normalize_entity_name("kyrko  herde") == "kyrko herde"


class TestDeduplicateEntities:
    def test_entity_persist_dedup_primary_wins_over_mentioned(self) -> None:
        entities = [
            _entity("kyrkoherde", relevance=Relevance.MENTIONED),
            _entity("kyrkoherde", relevance=Relevance.PRIMARY),
        ]
        result = _deduplicate_entities(entities)
        assert len(result) == 1
        assert result[0].relevance == Relevance.PRIMARY

    def test_entity_persist_dedup_keeps_distinct_types(self) -> None:
        entities = [
            _entity("kyrkoherde", EntityType.ROLE),
            _entity("kyrkoherde", EntityType.LEGAL_CONCEPT),
        ]
        result = _deduplicate_entities(entities)
        assert len(result) == 2

    def test_entity_persist_dedup_case_insensitive(self) -> None:
        entities = [
            _entity("Kyrkoherde", relevance=Relevance.MENTIONED),
            _entity("kyrkoherde", relevance=Relevance.PRIMARY),
        ]
        result = _deduplicate_entities(entities)
        assert len(result) == 1


class TestPersistEntities:
    async def test_entity_persist_calls_entity_repo_upsert_per_entity(self) -> None:
        entity_read = _entity_read("kyrkoherde")
        entity_repo = MagicMock()
        entity_repo.upsert = AsyncMock(return_value=entity_read)
        doc_entity_repo = MagicMock()
        doc_entity_repo.upsert = AsyncMock()

        doc_id = uuid.uuid4()
        entities = [_entity("Kyrkoherde"), _entity("Stiftet", EntityType.PARISH)]

        await persist_entities(entity_repo, doc_entity_repo, doc_id, entities)

        assert entity_repo.upsert.call_count == 2

    async def test_entity_persist_calls_doc_entity_repo_upsert_per_entity(self) -> None:
        entity_read = _entity_read("kyrkoherde")
        entity_repo = MagicMock()
        entity_repo.upsert = AsyncMock(return_value=entity_read)
        doc_entity_repo = MagicMock()
        doc_entity_repo.upsert = AsyncMock()

        doc_id = uuid.uuid4()
        entities = [_entity("Kyrkoherde"), _entity("Stiftet", EntityType.PARISH)]

        await persist_entities(entity_repo, doc_entity_repo, doc_id, entities)

        assert doc_entity_repo.upsert.call_count == 2

    async def test_entity_persist_normalizes_name_before_upsert(self) -> None:
        entity_read = _entity_read("kyrkoherde")
        entity_repo = MagicMock()
        entity_repo.upsert = AsyncMock(return_value=entity_read)
        doc_entity_repo = MagicMock()
        doc_entity_repo.upsert = AsyncMock()

        await persist_entities(entity_repo, doc_entity_repo, uuid.uuid4(), [_entity("  KYRKOHERDE  ")])

        create_dto = entity_repo.upsert.call_args[0][0]
        assert create_dto.name == "kyrkoherde"

    async def test_entity_persist_deduplicates_within_batch(self) -> None:
        entity_read = _entity_read("kyrkoherde")
        entity_repo = MagicMock()
        entity_repo.upsert = AsyncMock(return_value=entity_read)
        doc_entity_repo = MagicMock()
        doc_entity_repo.upsert = AsyncMock()

        entities = [
            _entity("kyrkoherde", relevance=Relevance.MENTIONED),
            _entity("kyrkoherde", relevance=Relevance.PRIMARY),
        ]
        await persist_entities(entity_repo, doc_entity_repo, uuid.uuid4(), entities)

        assert entity_repo.upsert.call_count == 1
        doc_create_dto = doc_entity_repo.upsert.call_args[0][0]
        assert doc_create_dto.relevance == "primary"

    async def test_entity_persist_empty_entities_does_nothing(self) -> None:
        entity_repo = MagicMock()
        entity_repo.upsert = AsyncMock()
        doc_entity_repo = MagicMock()
        doc_entity_repo.upsert = AsyncMock()

        await persist_entities(entity_repo, doc_entity_repo, uuid.uuid4(), [])

        entity_repo.upsert.assert_not_called()
        doc_entity_repo.upsert.assert_not_called()
