from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from _fsrepos import document as fs_document
from _fsrepos import document_entity as fs_document_entity
from _fsrepos import entity as fs_entity
from _fsrepos import task as fs_task
from _fsrepos import unresolved_reference as fs_unresolved
from _fsstore import FsSession, FsStore
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate
from shared.dtos.entity import EntityCreate
from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.dtos.unresolved_reference import UnresolvedReferenceCreate


def _session(store: FsStore) -> AsyncSession:
    # The fs repo functions expect the AsyncSession handle that run_step injects; at
    # runtime it is an FsSession, cast to satisfy the shared signatures.
    return cast(AsyncSession, FsSession(store))


async def test_persist_reload_roundtrip(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = _session(store)
    doc = await fs_document.create(
        session, DocumentCreate(source_url="https://example.com/a.pdf")
    )
    await session.commit()

    reloaded = FsStore(tmp_path)
    again = await fs_document.get_by_id(_session(reloaded), doc.id)
    assert again is not None
    assert again.id == doc.id
    assert again.source_url == "https://example.com/a.pdf"


async def test_get_by_case_number(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = _session(store)
    doc = await fs_document.create(
        session, DocumentCreate(source_url="https://example.com/a.pdf")
    )
    await fs_document.update(session, doc.id, DocumentUpdate(case_number="123-45"))

    found = await fs_document.get_by_case_number(session, "123-45")
    assert found is not None and found.id == doc.id
    assert await fs_document.get_by_case_number(session, "999-99") is None


async def test_update_is_partial(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = _session(store)
    doc = await fs_document.create(
        session, DocumentCreate(source_url="https://example.com/a.pdf")
    )

    updated = await fs_document.update(
        session, doc.id, DocumentUpdate(raw_text="hello")
    )
    assert updated is not None
    assert updated.raw_text == "hello"
    assert updated.source_url == doc.source_url  # untouched fields preserved
    assert updated.case_number is None


async def test_rollback_discards_uncommitted(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = _session(store)
    doc = await fs_document.create(
        session, DocumentCreate(source_url="https://example.com/a.pdf")
    )
    await session.commit()

    await fs_document.update(session, doc.id, DocumentUpdate(raw_text="should vanish"))
    await session.rollback()

    current = await fs_document.get_by_id(session, doc.id)
    assert current is not None
    assert current.raw_text is None


async def test_task_reset_and_clear(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = _session(store)
    doc_id = uuid4()
    task = await fs_task.create(
        session, TaskCreate(document_id=doc_id, step="parse", status="pending")
    )
    await fs_task.update_status(session, task.id, TaskStatusUpdate(status="completed"))

    reset_id = await fs_task.reset_to_pending(session, doc_id, "parse")
    assert reset_id == task.id
    after = await fs_task.get_by_id(session, task.id)
    assert after is not None
    assert after.status == "pending"
    assert after.completed_at is None

    await fs_task.delete_by_document_and_step(session, doc_id, "parse")
    assert await fs_task.get_by_document_and_step(session, doc_id, "parse") is None


async def test_entity_upsert_dedups_on_name_and_type(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = _session(store)
    first = await fs_entity.upsert(
        session, EntityCreate(name="Domkapitlet", type="organization")
    )
    second = await fs_entity.upsert(
        session, EntityCreate(name="Domkapitlet", type="organization")
    )
    assert first.id == second.id
    assert len(store.rows["entities"]) == 1


async def test_document_entity_upgrades_relevance_to_primary(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = _session(store)
    doc_id, entity_id = uuid4(), uuid4()
    await fs_document_entity.upsert(
        session,
        DocumentEntityCreate(
            document_id=doc_id, entity_id=entity_id, relevance="secondary"
        ),
    )
    upgraded = await fs_document_entity.upsert(
        session,
        DocumentEntityCreate(
            document_id=doc_id, entity_id=entity_id, relevance="primary"
        ),
    )
    assert upgraded.relevance == "primary"
    assert len(store.rows["document_entities"]) == 1


async def test_unresolved_upsert_get_and_delete(tmp_path: Path) -> None:
    store = FsStore(tmp_path)
    session = _session(store)
    doc_id = uuid4()
    first = await fs_unresolved.upsert(
        session,
        UnresolvedReferenceCreate(
            source_document_id=doc_id, target_case_number="123-45"
        ),
    )
    again = await fs_unresolved.upsert(
        session,
        UnresolvedReferenceCreate(
            source_document_id=doc_id, target_case_number="123-45"
        ),
    )
    assert first.id == again.id

    found = await fs_unresolved.get_by_target_case_number(session, "123-45")
    assert len(found) == 1

    await fs_unresolved.delete(session, first.id)
    assert await fs_unresolved.get_by_target_case_number(session, "123-45") == []
