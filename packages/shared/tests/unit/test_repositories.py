import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.entity import EntityCreate
from shared.dtos.task import TaskStatusUpdate
from shared.repositories import chunk as chunk_repo
from shared.repositories import document as document_repo
from shared.repositories import entity as entity_repo
from shared.repositories import task as task_repo


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    return session


def _mock_document(**kwargs):
    now = datetime.now(tz=timezone.utc)
    defaults = dict(
        id=uuid.uuid4(),
        source_url="https://example.com",
        source_document_id=None,
        source_headline=None,
        source_decision_number=None,
        source_published_at=None,
        gcs_uri=None,
        raw_text=None,
        summary=None,
        case_number=None,
        decision_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=now,
        updated_at=now,
    )
    return SimpleNamespace(**{**defaults, **kwargs})


def _mock_task(**kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        step="crawl",
        status="pending",
        error_message=None,
        started_at=None,
        completed_at=None,
    )
    return SimpleNamespace(**{**defaults, **kwargs})


class TestDocumentRepository:
    @pytest.mark.asyncio
    async def test_create_adds_and_returns_dto(self):
        session = _make_session()
        doc = _mock_document()
        session.refresh = AsyncMock(
            side_effect=lambda obj: setattr(obj, "id", doc.id) or None
        )

        async def side_effect_refresh(obj):
            for k, v in vars(doc).items():
                setattr(obj, k, v)

        session.refresh.side_effect = side_effect_refresh
        dto = await document_repo.create(
            session, DocumentCreate(source_url="https://example.com")
        )

        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert dto.source_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_update_only_sets_non_none_fields(self):
        session = _make_session()
        doc = _mock_document(gcs_uri=None)
        session.get.return_value = doc

        async def refresh(_obj):
            pass

        session.refresh.side_effect = refresh

        update = DocumentUpdate(gcs_uri="gs://bucket/file.pdf")
        await document_repo.update(session, doc.id, update)

        assert doc.gcs_uri == "gs://bucket/file.pdf"
        assert doc.raw_text is None

    @pytest.mark.asyncio
    async def test_update_returns_none_for_missing(self):
        session = _make_session()
        session.get.return_value = None
        result = await document_repo.update(
            session, uuid.uuid4(), DocumentUpdate(gcs_uri="x")
        )
        assert result is None


class TestTaskRepository:
    @pytest.mark.asyncio
    async def test_update_status_sets_started_at_for_processing(self):
        session = _make_session()
        task = _mock_task()
        session.get.return_value = task

        async def refresh(_obj):
            pass

        session.refresh.side_effect = refresh

        await task_repo.update_status(
            session, task.id, TaskStatusUpdate(status="processing")
        )

        assert task.started_at is not None
        assert task.completed_at is None

    @pytest.mark.asyncio
    async def test_update_status_sets_completed_at_for_completed(self):
        session = _make_session()
        task = _mock_task()
        session.get.return_value = task

        async def refresh(_obj):
            pass

        session.refresh.side_effect = refresh

        await task_repo.update_status(
            session, task.id, TaskStatusUpdate(status="completed")
        )

        assert task.completed_at is not None
        assert task.started_at is None


class TestChunkRepository:
    @pytest.mark.asyncio
    async def test_bulk_create_uses_add_all(self):
        session = _make_session()
        doc_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)
        dtos = [
            ChunkCreate(
                document_id=doc_id, chunk_index=0, chunk_text="first", embedding=[0.1]
            ),
            ChunkCreate(
                document_id=doc_id, chunk_index=1, chunk_text="second", embedding=[0.2]
            ),
        ]

        call_count = 0

        async def refresh(obj):
            nonlocal call_count
            obj.id = uuid.uuid4()
            obj.created_at = now
            call_count += 1

        session.refresh.side_effect = refresh

        results = await chunk_repo.bulk_create(session, dtos)

        session.add_all.assert_called_once()
        assert len(results) == 2
        assert results[0].chunk_text == "first"
        assert results[1].chunk_text == "second"


class TestEntityRepository:
    @pytest.mark.asyncio
    async def test_upsert_creates_new_entity(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        now = datetime.now(tz=timezone.utc)

        async def refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = now

        session.refresh.side_effect = refresh

        entity = await entity_repo.upsert(
            session, EntityCreate(name="kyrkorådet", type="role")
        )

        session.add.assert_called_once()
        assert entity.name == "kyrkorådet"

    @pytest.mark.asyncio
    async def test_upsert_returns_existing_entity(self):
        session = _make_session()
        now = datetime.now(tz=timezone.utc)
        existing = SimpleNamespace(
            id=uuid.uuid4(), name="kyrkorådet", type="role", created_at=now
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        session.execute.return_value = result_mock

        entity = await entity_repo.upsert(
            session, EntityCreate(name="kyrkorådet", type="role")
        )

        session.add.assert_not_called()
        assert entity.name == "kyrkorådet"
        assert entity.id == existing.id
