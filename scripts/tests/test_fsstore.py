from pathlib import Path
from uuid import uuid4

from _fsstore import (
    FsDocumentEntityRepository,
    FsDocumentRepository,
    FsEntityRepository,
    FsSession,
    FsStore,
    FsTaskRepository,
    FsUnresolvedReferenceRepository,
)
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate
from shared.dtos.entity import EntityCreate
from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.dtos.unresolved_reference import UnresolvedReferenceCreate


async def test_persist_reload_roundtrip(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    repo = FsDocumentRepository(store)
    doc = await repo.create(DocumentCreate(source_url="https://example.com/a.pdf"))
    await FsSession(store).commit()

    reloaded = FsStore(tmp_path)
    again = await FsDocumentRepository(reloaded).get_by_id(doc.id)
    assert again is not None
    assert again.id == doc.id
    assert again.source_url == "https://example.com/a.pdf"


async def test_get_by_case_number(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    repo = FsDocumentRepository(store)
    doc = await repo.create(DocumentCreate(source_url="https://example.com/a.pdf"))
    await repo.update(doc.id, DocumentUpdate(case_number="123-45"))

    found = await repo.get_by_case_number("123-45")
    assert found is not None and found.id == doc.id
    assert await repo.get_by_case_number("999-99") is None


async def test_update_is_partial(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    repo = FsDocumentRepository(store)
    doc = await repo.create(DocumentCreate(source_url="https://example.com/a.pdf"))

    updated = await repo.update(doc.id, DocumentUpdate(raw_text="hello"))
    assert updated is not None
    assert updated.raw_text == "hello"
    assert updated.source_url == doc.source_url  # untouched fields preserved
    assert updated.case_number is None


async def test_rollback_discards_uncommitted(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = FsSession(store)
    repo = FsDocumentRepository(store)
    doc = await repo.create(DocumentCreate(source_url="https://example.com/a.pdf"))
    await session.commit()

    await repo.update(doc.id, DocumentUpdate(raw_text="should vanish"))
    await session.rollback()

    current = await repo.get_by_id(doc.id)
    assert current is not None
    assert current.raw_text is None


async def test_task_reset_and_clear(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    repo = FsTaskRepository(store)
    doc_id = uuid4()
    task = await repo.create(TaskCreate(document_id=doc_id, step="parse", status="pending"))
    await repo.update_status(task.id, TaskStatusUpdate(status="completed"))

    reset_id = await repo.reset_to_pending(doc_id, "parse")
    assert reset_id == task.id
    after = await repo.get_by_id(task.id)
    assert after is not None
    assert after.status == "pending"
    assert after.completed_at is None

    await repo.delete_by_document_and_step(doc_id, "parse")
    assert await repo.get_by_document_and_step(doc_id, "parse") is None


async def test_entity_upsert_dedups_on_name_and_type(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    repo = FsEntityRepository(store)
    first = await repo.upsert(EntityCreate(name="Domkapitlet", type="organization"))
    second = await repo.upsert(EntityCreate(name="Domkapitlet", type="organization"))
    assert first.id == second.id
    assert len(store.rows["entities"]) == 1


async def test_document_entity_upgrades_relevance_to_primary(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    repo = FsDocumentEntityRepository(store)
    doc_id, entity_id = uuid4(), uuid4()
    await repo.upsert(
        DocumentEntityCreate(document_id=doc_id, entity_id=entity_id, relevance="secondary")
    )
    upgraded = await repo.upsert(
        DocumentEntityCreate(document_id=doc_id, entity_id=entity_id, relevance="primary")
    )
    assert upgraded.relevance == "primary"
    assert len(store.rows["document_entities"]) == 1


async def test_unresolved_upsert_get_and_delete(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    repo = FsUnresolvedReferenceRepository(store)
    doc_id = uuid4()
    first = await repo.upsert(
        UnresolvedReferenceCreate(source_document_id=doc_id, target_case_number="123-45")
    )
    again = await repo.upsert(
        UnresolvedReferenceCreate(source_document_id=doc_id, target_case_number="123-45")
    )
    assert first.id == again.id

    found = await repo.get_by_target_case_number("123-45")
    assert len(found) == 1

    await repo.delete(first.id)
    assert await repo.get_by_target_case_number("123-45") == []
