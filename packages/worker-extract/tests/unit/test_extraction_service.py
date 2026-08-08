from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from shared.dtos.document import DocumentRead
from shared.dtos.task import TaskRead
from shared.queue.base import QueueMessage
from ai.dtos import EntityResult, ExtractedEntity
from shared.enums import EntityRelevance, EntityType, PipelineStep
from worker_extract.services.extraction_service import process_extraction


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_doc(
    document_id: uuid.UUID | None = None,
    raw_text: str | None = "Kyrkoherden överklagade ärende ÖN 2021-0001.",
    case_number: str | None = "ÖN 2023-0042",
) -> DocumentRead:
    return DocumentRead(
        id=document_id or uuid.uuid4(),
        source_url="https://example.com/doc.pdf",
        source_document_id=None,
        source_headline=None,
        source_published_at=None,
        gcs_uri=None,
        raw_text=raw_text,
        summary=None,
        case_number=case_number,
        decision_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_task(
    document_id: uuid.UUID,
    step: str = "extract",
    status: str = "pending",
) -> TaskRead:
    return TaskRead(
        id=uuid.uuid4(),
        document_id=document_id,
        step=step,
        status=status,
        error_message=None,
        started_at=None,
        completed_at=None,
    )


def _make_repos(
    task: TaskRead | None,
    document: DocumentRead | None,
) -> tuple[
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    doc_repo = MagicMock()
    doc_repo.get_by_id = AsyncMock(return_value=document)
    doc_repo.get_by_case_number = AsyncMock(return_value=None)

    task_repo = MagicMock()
    task_repo.get_by_id = AsyncMock(return_value=task)
    task_repo.get_by_document_and_step = AsyncMock(return_value=None)
    task_repo.update_status = AsyncMock()
    if document is not None:
        task_repo.create = AsyncMock(return_value=_make_task(document.id, step="chunk"))
    else:
        task_repo.create = AsyncMock()

    entity_repo = MagicMock()
    entity_repo.upsert = AsyncMock()
    doc_entity_repo = MagicMock()
    doc_entity_repo.upsert = AsyncMock()
    doc_entity_repo.delete_missing_for_document = AsyncMock()
    ref_repo = MagicMock()
    ref_repo.upsert = AsyncMock()
    unresolved_repo = MagicMock()
    unresolved_repo.upsert = AsyncMock()
    unresolved_repo.get_by_target_case_number = AsyncMock(return_value=[])
    unresolved_repo.delete = AsyncMock()

    publisher = MagicMock()

    return (
        session,
        doc_repo,
        task_repo,
        entity_repo,
        doc_entity_repo,
        ref_repo,
        unresolved_repo,
        publisher,
    )


_EMPTY_RESULT = EntityResult(entities=[], references=[])


async def _call(
    document_id: uuid.UUID,
    task_id: uuid.UUID,
    session: MagicMock,
    doc_repo: MagicMock,
    task_repo: MagicMock,
    entity_repo: MagicMock,
    doc_entity_repo: MagicMock,
    ref_repo: MagicMock,
    unresolved_repo: MagicMock,
    publisher: MagicMock,
    next_topic: PipelineStep = PipelineStep.CHUNK,
    strategy_result: EntityResult = _EMPTY_RESULT,
) -> None:
    await process_extraction(
        document_id=document_id,
        task_id=task_id,
        document_repo=doc_repo,
        task_repo=task_repo,
        entity_repo=entity_repo,
        doc_entity_repo=doc_entity_repo,
        ref_repo=ref_repo,
        unresolved_repo=unresolved_repo,
        queue_publisher=publisher,
        session=session,
        strategy=AsyncMock(return_value=strategy_result),
        next_topic=next_topic,
    )


class TestWorkerProcessesDocument:
    async def test_worker_processes_document_end_to_end(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id)
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)

        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        )

        doc_repo.get_by_id.assert_called_once_with(session, doc.id)
        task_repo.create.assert_called_once()
        publisher.publish.assert_called_once()

    async def test_worker_publishes_to_next_topic_on_success(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id)
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)

        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
            next_topic=PipelineStep.CHUNK,
        )

        publisher.publish.assert_called_once()
        topic, msg = publisher.publish.call_args[0]
        assert topic == "chunk"
        assert isinstance(msg, QueueMessage)
        assert msg.document_id == doc.id

    async def test_worker_does_not_publish_on_failure(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id)
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)
        entity_repo.upsert = AsyncMock(side_effect=RuntimeError("db error"))

        with patch(
            "worker_extract.services.extraction_service.persist_entities",
            AsyncMock(side_effect=RuntimeError("db error")),
        ):
            await process_extraction(
                document_id=doc.id,
                task_id=task.id,
                document_repo=doc_repo,
                task_repo=task_repo,
                entity_repo=entity_repo,
                doc_entity_repo=doc_entity_repo,
                ref_repo=ref_repo,
                unresolved_repo=unresolved_repo,
                queue_publisher=publisher,
                session=session,
                strategy=AsyncMock(return_value=_EMPTY_RESULT),
                next_topic=PipelineStep.CHUNK,
            )

        publisher.publish.assert_not_called()

    async def test_worker_document_not_found_marks_failed_no_publish(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id)
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, None)

        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        )

        publisher.publish.assert_not_called()
        status_calls = [c[0][2] for c in task_repo.update_status.call_args_list]
        assert any(s.status == "failed" for s in status_calls)

    async def test_worker_no_raw_text_marks_failed_no_publish(self) -> None:
        doc = _make_doc(raw_text=None)
        task = _make_task(doc.id)
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)

        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        )

        publisher.publish.assert_not_called()
        status_calls = [c[0][2] for c in task_repo.update_status.call_args_list]
        assert any(s.status == "failed" for s in status_calls)


class TestCheckpointing:
    async def test_checkpoint_transitions_to_processing(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id)
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)

        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        )

        status_calls = [c[0][2].status for c in task_repo.update_status.call_args_list]
        assert "processing" in status_calls

    async def test_checkpoint_transitions_to_completed_on_success(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id)
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)

        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        )

        status_calls = [c[0][2].status for c in task_repo.update_status.call_args_list]
        assert status_calls[-1] == "completed"

    async def test_checkpoint_transitions_to_failed_on_exception(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id)
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)

        with patch(
            "worker_extract.services.extraction_service.persist_entities",
            AsyncMock(side_effect=RuntimeError("extraction exploded")),
        ):
            await process_extraction(
                document_id=doc.id,
                task_id=task.id,
                document_repo=doc_repo,
                task_repo=task_repo,
                entity_repo=entity_repo,
                doc_entity_repo=doc_entity_repo,
                ref_repo=ref_repo,
                unresolved_repo=unresolved_repo,
                queue_publisher=publisher,
                session=session,
                strategy=AsyncMock(return_value=_EMPTY_RESULT),
                next_topic=PipelineStep.CHUNK,
            )

        session.rollback.assert_called_once()
        status_calls = [c[0][2] for c in task_repo.update_status.call_args_list]
        last = status_calls[-1]
        assert last.status == "failed"
        assert "extraction exploded" in last.error_message

    async def test_checkpoint_skips_completed_task(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id, status="completed")
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)

        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        )

        doc_repo.get_by_id.assert_not_called()
        publisher.publish.assert_not_called()
        task_repo.update_status.assert_not_called()

    async def test_checkpoint_retries_failed_task(self) -> None:
        doc = _make_doc()
        task = _make_task(doc.id, status="failed")
        (
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        ) = _make_repos(task, doc)

        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
        )

        status_calls = [c[0][2].status for c in task_repo.update_status.call_args_list]
        assert "processing" in status_calls
        assert status_calls[-1] == "completed"


_TRAILER_TEXT = (
    "Kyrkoherden överklagade beslutet.\n"
    "Sökord: Utlämnande av handlingar, Jäv.\n"
    "Ärendenummer: ÖN 2023-0042\n"
    "Beslut: 1/2026\n"
)


async def _persisted_entities(
    raw_text: str,
    strategy_result: EntityResult = _EMPTY_RESULT,
) -> list[ExtractedEntity]:
    """Run the step and hand back what reached `persist_entities`."""
    doc = _make_doc(raw_text=raw_text)
    task = _make_task(doc.id)
    (
        session,
        doc_repo,
        task_repo,
        entity_repo,
        doc_entity_repo,
        ref_repo,
        unresolved_repo,
        publisher,
    ) = _make_repos(task, doc)

    persist = AsyncMock()
    with patch("worker_extract.services.extraction_service.persist_entities", persist):
        await _call(
            doc.id,
            task.id,
            session,
            doc_repo,
            task_repo,
            entity_repo,
            doc_entity_repo,
            ref_repo,
            unresolved_repo,
            publisher,
            strategy_result=strategy_result,
        )

    # persist_entities(session, entity_repo, doc_entity_repo, document_id, entities)
    return persist.call_args[0][4]


class TestKeywordExtraction:
    async def test_trailer_keywords_are_persisted_as_primary(self) -> None:
        entities = await _persisted_entities(_TRAILER_TEXT)

        keywords = [e for e in entities if e.type == EntityType.KEYWORD]
        assert [e.name for e in keywords] == ["Utlämnande av handlingar", "Jäv"]
        assert all(e.relevance == EntityRelevance.PRIMARY for e in keywords)

    async def test_keywords_are_extracted_alongside_strategy_entities(self) -> None:
        # Keywords are read off the trailer, not produced by the strategy, so an
        # LLM run must yield the same ones a rule-based run does.
        inferred = ExtractedEntity(
            name="jäv",
            type=EntityType.LEGAL_CONCEPT,
            relevance=EntityRelevance.MENTIONED,
        )
        entities = await _persisted_entities(
            _TRAILER_TEXT, EntityResult(entities=[inferred], references=[])
        )

        assert inferred in entities
        assert any(e.type == EntityType.KEYWORD for e in entities)

    async def test_a_keyword_the_strategy_invented_is_dropped(self) -> None:
        # `parsing.py` validates LLM types against EntityType, so `keyword` would
        # otherwise pass — but only the trailer may declare one.
        hallucinated = ExtractedEntity(
            name="påhittat",
            type=EntityType.KEYWORD,
            relevance=EntityRelevance.PRIMARY,
        )
        entities = await _persisted_entities(
            _TRAILER_TEXT, EntityResult(entities=[hallucinated], references=[])
        )

        assert "påhittat" not in [e.name for e in entities]

    async def test_a_decision_without_sokord_yields_no_keywords(self) -> None:
        entities = await _persisted_entities(
            "Beslut i ärendet.\nÄrendenummer: ÖN 2023-0042\n"
        )
        assert [e for e in entities if e.type == EntityType.KEYWORD] == []
