import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from shared.dtos.chunk import ChunkCreate, ChunkRead
from shared.dtos.document import DocumentCreate, DocumentRead, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate, DocumentEntityRead
from shared.dtos.document_reference import (
    DocumentReferenceCreate,
    DocumentReferenceRead,
)
from shared.dtos.entity import EntityCreate, EntityRead
from shared.dtos.session import SessionCreate, SessionRead, SessionUpdate
from shared.dtos.task import TaskCreate, TaskRead, TaskStatusUpdate


class TestDocumentDTOs:
    def test_create_requires_source_url(self):
        with pytest.raises(ValidationError):
            DocumentCreate()  # type: ignore[call-arg]

    def test_create_valid(self):
        dto = DocumentCreate(source_url="https://example.com")
        assert dto.source_url == "https://example.com"

    def test_update_all_optional(self):
        dto = DocumentUpdate()
        assert dto.gcs_uri is None
        assert dto.raw_text is None
        assert dto.decision_date is None

    def test_read_from_attributes(self):
        now = datetime.now(tz=timezone.utc)
        obj = SimpleNamespace(
            id=uuid.uuid4(),
            source_url="https://example.com",
            source_document_id=None,
            source_headline=None,
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
        dto = DocumentRead.model_validate(obj)
        assert dto.source_url == "https://example.com"
        assert dto.created_at == now


class TestTaskDTOs:
    def test_create_requires_document_id_and_step(self):
        with pytest.raises(ValidationError):
            TaskCreate()  # type: ignore[call-arg]

    def test_create_defaults_status_to_pending(self):
        dto = TaskCreate(document_id=uuid.uuid4(), step="crawl")
        assert dto.status == "pending"

    def test_status_update_all_optional_except_status(self):
        dto = TaskStatusUpdate(status="processing")
        assert dto.error_message is None

    def test_read_from_attributes(self):
        obj = SimpleNamespace(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            step="crawl",
            status="pending",
            error_message=None,
            started_at=None,
            completed_at=None,
        )
        dto = TaskRead.model_validate(obj)
        assert dto.step == "crawl"
        assert dto.started_at is None


class TestChunkDTOs:
    def test_create_requires_document_id_chunk_index_and_text(self):
        with pytest.raises(ValidationError):
            ChunkCreate()  # type: ignore[call-arg]

    def test_create_with_embedding(self):
        dto = ChunkCreate(
            document_id=uuid.uuid4(),
            chunk_index=0,
            chunk_text="test",
            embedding=[0.1, 0.2, 0.3],
        )
        assert dto.embedding == [0.1, 0.2, 0.3]

    def test_create_embedding_optional(self):
        dto = ChunkCreate(document_id=uuid.uuid4(), chunk_index=0, chunk_text="test")
        assert dto.embedding is None

    def test_read_from_attributes(self):
        now = datetime.now(tz=timezone.utc)
        obj = SimpleNamespace(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            chunk_index=0,
            chunk_text="hello",
            contextual_text=None,
            embedding=[0.1],
            section="body",
            appendix_label=None,
            created_at=now,
        )
        dto = ChunkRead.model_validate(obj)
        assert dto.chunk_text == "hello"


class TestEntityDTOs:
    def test_create_requires_name_and_type(self):
        with pytest.raises(ValidationError):
            EntityCreate()  # type: ignore[call-arg]

    def test_read_from_attributes(self):
        now = datetime.now(tz=timezone.utc)
        obj = SimpleNamespace(
            id=uuid.uuid4(), name="kyrkorådet", type="role", created_at=now
        )
        dto = EntityRead.model_validate(obj)
        assert dto.name == "kyrkorådet"
        assert dto.type == "role"


class TestDocumentEntityDTOs:
    def test_create_requires_all_fields(self):
        with pytest.raises(ValidationError):
            DocumentEntityCreate()  # type: ignore[call-arg]

    def test_read_from_attributes(self):
        obj = SimpleNamespace(
            document_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            relevance="primary",
        )
        dto = DocumentEntityRead.model_validate(obj)
        assert dto.relevance == "primary"


class TestDocumentReferenceDTOs:
    def test_create_requires_source_and_target(self):
        with pytest.raises(ValidationError):
            DocumentReferenceCreate()  # type: ignore[call-arg]

    def test_create_context_optional(self):
        dto = DocumentReferenceCreate(
            source_document_id=uuid.uuid4(),
            target_document_id=uuid.uuid4(),
        )
        assert dto.reference_context is None

    def test_read_from_attributes(self):
        obj = SimpleNamespace(
            source_document_id=uuid.uuid4(),
            target_document_id=uuid.uuid4(),
            reference_context="see decision 123",
        )
        dto = DocumentReferenceRead.model_validate(obj)
        assert dto.reference_context == "see decision 123"


class TestSessionDTOs:
    def test_create_defaults_empty_history(self):
        dto = SessionCreate()
        assert dto.history == []

    def test_update_all_optional(self):
        dto = SessionUpdate()
        assert dto.last_active_at is None
        assert dto.history is None

    def test_read_from_attributes(self):
        now = datetime.now(tz=timezone.utc)
        obj = SimpleNamespace(
            id=uuid.uuid4(),
            created_at=now,
            last_active_at=now,
            history=[{"role": "user", "content": "hello"}],
        )
        dto = SessionRead.model_validate(obj)
        assert len(dto.history) == 1
        assert dto.history[0]["role"] == "user"
