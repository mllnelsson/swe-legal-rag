from __future__ import annotations
from shared.enums import EntityRelevance, EntityType, PipelineStep

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.document import DocumentCreate, DocumentRead, DocumentUpdate
from shared.dtos.task import TaskCreate, TaskRead
from shared.testing.pipeline import redrive_task
from shared.models.document_entity import DocumentEntity
from shared.models.document_reference import DocumentReference
from shared.models.entity import Entity
from shared.models.task import Task
from shared.models.unresolved_reference import UnresolvedReference
from shared.queue.base import QueueMessage
from shared.queue.base import QueuePublisher
from worker_extract.extractors.rule_based import extract_rule_based_strategy
from worker_extract.services.extraction_service import process_extraction
from worker_extract.services.reference_service import reconcile_references

# Text rich enough for rule-based extraction to find entities
_ENTITY_RICH_TEXT = (
    "Överklagandenämnden för Svenska kyrkan\n\n"
    "Kyrkoherden i Skattkärrens församling överklagade Göteborgs stifts beslut om tjänstetillsättning. "
    "Ärendet rör frågan om behörighet och överklagande. "
    "Beslutet fattades med hänvisning till kyrkoordningen kapitel 32 § 5.\n\n"
    "Nämnden avslår överklagandet."
)


async def _run_extraction(
    session: AsyncSession,
    document_repo,
    task_repo,
    entity_repo,
    doc_entity_repo,
    ref_repo,
    unresolved_repo,
    sync_publisher: QueuePublisher,
    *,
    raw_text: str,
    case_number: str | None = None,
) -> tuple[DocumentRead, TaskRead]:
    doc = await document_repo.create(
        session,
        DocumentCreate(source_url=f"https://example.com/{case_number or 'doc'}.pdf"),
    )
    await document_repo.update(
        session, doc.id, DocumentUpdate(raw_text=raw_text, case_number=case_number)
    )
    await session.commit()
    doc = await document_repo.get_by_id(session, doc.id)
    assert doc is not None

    task = await task_repo.create(
        session, TaskCreate(document_id=doc.id, step="extract", status="pending")
    )
    await session.commit()

    await process_extraction(
        document_id=doc.id,
        task_id=task.id,
        document_repo=document_repo,
        task_repo=task_repo,
        entity_repo=entity_repo,
        doc_entity_repo=doc_entity_repo,
        ref_repo=ref_repo,
        unresolved_repo=unresolved_repo,
        queue_publisher=sync_publisher,
        session=session,
        strategy=extract_rule_based_strategy,
        next_topic=PipelineStep.CHUNK,
    )
    return doc, task


async def test_extraction_populates_entities_and_completes_task(
    session: AsyncSession,
    document_repo,
    task_repo,
    entity_repo,
    doc_entity_repo,
    ref_repo,
    unresolved_repo,
    sync_publisher: QueuePublisher,
    published_messages: list[QueueMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRACT_STRATEGY", "rule_based")

    doc, task = await _run_extraction(
        session,
        document_repo,
        task_repo,
        entity_repo,
        doc_entity_repo,
        ref_repo,
        unresolved_repo,
        sync_publisher,
        raw_text=_ENTITY_RICH_TEXT,
        case_number="2023-0001",
    )

    entities = (await session.execute(select(Entity))).scalars().all()
    assert len(entities) >= 1

    doc_entities = (
        (
            await session.execute(
                select(DocumentEntity).where(DocumentEntity.document_id == doc.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(doc_entities) >= 1

    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.status == "completed"
    assert task_row.completed_at is not None

    assert len(published_messages) == 1
    assert published_messages[0].document_id == doc.id


async def test_extraction_cross_reference_resolution(
    session: AsyncSession,
    document_repo,
    task_repo,
    entity_repo,
    doc_entity_repo,
    ref_repo,
    unresolved_repo,
    sync_publisher: QueuePublisher,
    published_messages: list[QueueMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRACT_STRATEGY", "rule_based")

    # Insert document A (the target)
    doc_a = await document_repo.create(
        session, DocumentCreate(source_url="https://example.com/doc_a.pdf")
    )
    await document_repo.update(
        session, doc_a.id, DocumentUpdate(case_number="2020-0100")
    )
    await session.commit()

    # Document B cites document A's case number
    text_b = (
        "Kyrkoherden överklagade beslut om tjänstetillsättning. "
        "Se även avgörandet i ärende ÖN 2020-0100 för liknande situation."
    )
    doc_b, _ = await _run_extraction(
        session,
        document_repo,
        task_repo,
        entity_repo,
        doc_entity_repo,
        ref_repo,
        unresolved_repo,
        sync_publisher,
        raw_text=text_b,
        case_number="2021-0200",
    )

    refs = (
        (
            await session.execute(
                select(DocumentReference).where(
                    DocumentReference.source_document_id == doc_b.id,
                    DocumentReference.target_document_id == doc_a.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(refs) == 1


async def test_extraction_unresolved_reference(
    session: AsyncSession,
    document_repo,
    task_repo,
    entity_repo,
    doc_entity_repo,
    ref_repo,
    unresolved_repo,
    sync_publisher: QueuePublisher,
    published_messages: list[QueueMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRACT_STRATEGY", "rule_based")

    text_b = "Kyrkoherden överklagade beslut. Se även avgörandet i ärende ÖN 2099-9999."
    doc_b, _ = await _run_extraction(
        session,
        document_repo,
        task_repo,
        entity_repo,
        doc_entity_repo,
        ref_repo,
        unresolved_repo,
        sync_publisher,
        raw_text=text_b,
        case_number="2021-0200",
    )

    unresolved = (
        (
            await session.execute(
                select(UnresolvedReference).where(
                    UnresolvedReference.source_document_id == doc_b.id,
                    UnresolvedReference.target_case_number == "2099-9999",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(unresolved) == 1


async def test_extraction_reconciliation(
    session: AsyncSession,
    document_repo,
    task_repo,
    entity_repo,
    doc_entity_repo,
    ref_repo,
    unresolved_repo,
    sync_publisher: QueuePublisher,
    published_messages: list[QueueMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRACT_STRATEGY", "rule_based")

    # Document B has unresolved reference to ÖN 2099-9999
    text_b = "Kyrkoherden överklagade beslut. Se även avgörandet i ärende ÖN 2099-9999."
    doc_b, _ = await _run_extraction(
        session,
        document_repo,
        task_repo,
        entity_repo,
        doc_entity_repo,
        ref_repo,
        unresolved_repo,
        sync_publisher,
        raw_text=text_b,
        case_number="2021-0200",
    )

    unresolved_before = (
        (
            await session.execute(
                select(UnresolvedReference).where(
                    UnresolvedReference.target_case_number == "2099-9999"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(unresolved_before) == 1

    # Document C is ingested with case_number matching the unresolved ref
    doc_c = await document_repo.create(
        session, DocumentCreate(source_url="https://example.com/doc_c.pdf")
    )
    await document_repo.update(
        session, doc_c.id, DocumentUpdate(case_number="2099-9999")
    )
    await session.commit()
    doc_c = await document_repo.get_by_id(session, doc_c.id)
    assert doc_c is not None

    count = await reconcile_references(
        session, unresolved_repo, ref_repo, doc_c.id, ["2099-9999"]
    )
    await session.commit()

    assert count == 1

    refs = (
        (
            await session.execute(
                select(DocumentReference).where(
                    DocumentReference.source_document_id == doc_b.id,
                    DocumentReference.target_document_id == doc_c.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(refs) == 1

    unresolved_after = (
        (
            await session.execute(
                select(UnresolvedReference).where(
                    UnresolvedReference.target_case_number == "2099-9999"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(unresolved_after) == 0


async def test_extraction_idempotency(
    session: AsyncSession,
    document_repo,
    task_repo,
    entity_repo,
    doc_entity_repo,
    ref_repo,
    unresolved_repo,
    sync_publisher: QueuePublisher,
    published_messages: list[QueueMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRACT_STRATEGY", "rule_based")

    # First extraction run
    doc, task = await _run_extraction(
        session,
        document_repo,
        task_repo,
        entity_repo,
        doc_entity_repo,
        ref_repo,
        unresolved_repo,
        sync_publisher,
        raw_text=_ENTITY_RICH_TEXT,
        case_number="2023-0001",
    )

    entity_count_after_first = (
        await session.execute(select(func.count()).select_from(Entity))
    ).scalar_one()
    doc_entity_count_after_first = (
        await session.execute(
            select(func.count())
            .select_from(DocumentEntity)
            .where(DocumentEntity.document_id == doc.id)
        )
    ).scalar_one()
    assert entity_count_after_first >= 1

    # Second extraction run — the same task re-driven, same document
    await redrive_task(session, task_repo, task.id)

    await process_extraction(
        document_id=doc.id,
        task_id=task.id,
        document_repo=document_repo,
        task_repo=task_repo,
        entity_repo=entity_repo,
        doc_entity_repo=doc_entity_repo,
        ref_repo=ref_repo,
        unresolved_repo=unresolved_repo,
        queue_publisher=sync_publisher,
        session=session,
        strategy=extract_rule_based_strategy,
        next_topic=PipelineStep.CHUNK,
    )

    entity_count_after_second = (
        await session.execute(select(func.count()).select_from(Entity))
    ).scalar_one()
    doc_entity_count_after_second = (
        await session.execute(
            select(func.count())
            .select_from(DocumentEntity)
            .where(DocumentEntity.document_id == doc.id)
        )
    ).scalar_one()

    assert entity_count_after_second == entity_count_after_first
    assert doc_entity_count_after_second == doc_entity_count_after_first

    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.status == "completed"


# The same decision with the nämnd's trailer attached — kept separate from
# `_ENTITY_RICH_TEXT` so the idempotency test's entity counts stay stable.
_TRAILER_TEXT = (
    _ENTITY_RICH_TEXT + "\n"
    "Sökord: Tjänstetillsättning, Behörighet.\n"
    "Ärendenummer: ÖN 2023-0002\n"
    "Beslut: 4/2026\n"
)


async def test_extraction_stores_trailer_keywords_as_linked_entities(
    session: AsyncSession,
    document_repo,
    task_repo,
    entity_repo,
    doc_entity_repo,
    ref_repo,
    unresolved_repo,
    sync_publisher: QueuePublisher,
    published_messages: list[QueueMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRACT_STRATEGY", "rule_based")

    doc, _ = await _run_extraction(
        session,
        document_repo,
        task_repo,
        entity_repo,
        doc_entity_repo,
        ref_repo,
        unresolved_repo,
        sync_publisher,
        raw_text=_TRAILER_TEXT,
        case_number="2023-0002",
    )

    keywords = (
        (
            await session.execute(
                select(Entity)
                .join(DocumentEntity, DocumentEntity.entity_id == Entity.id)
                .where(
                    Entity.type == EntityType.KEYWORD,
                    DocumentEntity.document_id == doc.id,
                )
                .order_by(Entity.name)
            )
        )
        .scalars()
        .all()
    )

    # Normalized to lowercase by `persist_entities`, like every other entity.
    assert [k.name for k in keywords] == ["behörighet", "tjänstetillsättning"]

    edges = (
        (
            await session.execute(
                select(DocumentEntity)
                .join(Entity, DocumentEntity.entity_id == Entity.id)
                .where(
                    Entity.type == EntityType.KEYWORD,
                    DocumentEntity.document_id == doc.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert {edge.relevance for edge in edges} == {EntityRelevance.PRIMARY}

    # "behörighet" is also a known legal concept the rule-based extractor finds in
    # the body: the two must coexist as separate nodes, not collapse into one.
    concept = (
        await session.execute(
            select(Entity).where(
                Entity.name == "behörighet",
                Entity.type == EntityType.LEGAL_CONCEPT,
            )
        )
    ).scalar_one()
    assert concept.id not in {k.id for k in keywords}
