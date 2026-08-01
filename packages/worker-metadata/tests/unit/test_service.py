from __future__ import annotations
from shared.enums import PipelineStep

import datetime
import uuid
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

from shared.dtos.document import DocumentRead
from shared.dtos.task import TaskRead
from shared.queue.base import QueueMessage
from worker_metadata.patterns import MetadataResult
from worker_metadata.service import process_metadata

_SWEDISH_TEXT = (
    "ÖN 2023-0042\n\n"
    "Beslut den 15 januari 2023\n\n"
    "Ärende: Kyrkogårdsförvaltning\n\n"
    "Överklagandenämnden bifaller överklagandet och upphäver det överklagade beslutet."
)


def _make_doc_read(
    document_id: uuid.UUID | None = None,
    raw_text: str | None = _SWEDISH_TEXT,
) -> DocumentRead:
    now = datetime.datetime.now(tz=timezone.utc)
    return DocumentRead(
        id=document_id or uuid.uuid4(),
        source_url="https://example.com/decision.pdf",
        source_document_id=None,
        source_headline=None,
        source_published_at=None,
        gcs_uri="gs://bucket/documents/x/original.pdf",
        raw_text=raw_text,
        summary=None,
        case_number=None,
        decision_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=now,
        updated_at=now,
    )


def _make_task_read(
    document_id: uuid.UUID,
    step: str = "metadata",
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


def _make_deps(
    task: TaskRead | None,
    document: DocumentRead | None,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    doc_repo = MagicMock()
    doc_repo.get_by_id = AsyncMock(return_value=document)
    doc_repo.update = AsyncMock()

    task_repo = MagicMock()
    task_repo.get_by_id = AsyncMock(return_value=task)
    task_repo.get_by_document_and_step = AsyncMock(return_value=None)
    task_repo.update_status = AsyncMock()
    if document is not None:
        task_repo.create = AsyncMock(
            return_value=_make_task_read(document.id, step="extract")
        )
    else:
        task_repo.create = AsyncMock()

    publisher = MagicMock()

    return session, doc_repo, task_repo, publisher


async def _call(
    document_id: uuid.UUID,
    task_id: uuid.UUID,
    session: MagicMock,
    doc_repo: MagicMock,
    task_repo: MagicMock,
    publisher: MagicMock,
    rule_extractor: MagicMock,
    llm_extractor: AsyncMock,
) -> None:
    await process_metadata(
        document_id=document_id,
        task_id=task_id,
        document_repo=doc_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        rule_extractor=rule_extractor,
        llm_extractor=llm_extractor,
        session=session,
        next_topic=PipelineStep.EXTRACT,
    )


async def test_rule_based_succeeds_no_llm_called() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    session, doc_repo, task_repo, publisher = _make_deps(task, doc)

    complete_result = MetadataResult(
        case_number="2023-0042",
        decision_number=None,
        decision_date=datetime.date(2023, 1, 15),
        decision_outcome="bifaller överklagandet",
        category="Kyrkogårdsförvaltning",
    )
    rule_extractor = MagicMock(return_value=complete_result)
    llm_extractor = AsyncMock()

    await _call(
        doc.id,
        task.id,
        session,
        doc_repo,
        task_repo,
        publisher,
        rule_extractor,
        llm_extractor,
    )

    llm_extractor.assert_not_called()

    doc_repo.update.assert_called_once()
    _session, _doc_id, update_dto = doc_repo.update.call_args[0]
    assert update_dto.case_number == "2023-0042"
    assert update_dto.decision_date == datetime.date(2023, 1, 15)
    assert update_dto.decision_outcome == "bifaller överklagandet"
    assert update_dto.category == "Kyrkogårdsförvaltning"

    status_calls = [c[0][2] for c in task_repo.update_status.call_args_list]
    assert status_calls[-1].status == "completed"

    publisher.publish.assert_called_once()
    topic, msg = publisher.publish.call_args[0]
    assert topic == "extract"
    assert isinstance(msg, QueueMessage)
    assert msg.document_id == doc.id


async def test_partial_rule_based_llm_fills_gaps() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    session, doc_repo, task_repo, publisher = _make_deps(task, doc)

    rule_result = MetadataResult(
        case_number="2023-0042",
        decision_number=None,
        decision_date=datetime.date(2023, 1, 15),
    )
    rule_extractor = MagicMock(return_value=rule_result)

    llm_result = MetadataResult(
        decision_outcome="bifaller överklagandet",
        category="Kyrkogårdsförvaltning",
    )
    llm_extractor = AsyncMock(return_value=llm_result)

    await _call(
        doc.id,
        task.id,
        session,
        doc_repo,
        task_repo,
        publisher,
        rule_extractor,
        llm_extractor,
    )

    # The extractor gets the body and nothing else. It used to also receive the
    # list of missing fields, but no implementation ever read it — the prompt
    # asks for all four regardless — so the argument was dropped rather than
    # left as a promise the extractors do not keep. The missing list is still
    # logged, which is where it was actually doing work.
    llm_extractor.assert_called_once_with(_SWEDISH_TEXT)

    _session, _doc_id, update_dto = doc_repo.update.call_args[0]
    assert update_dto.case_number == "2023-0042"
    assert update_dto.decision_date == datetime.date(2023, 1, 15)
    assert update_dto.decision_outcome == "bifaller överklagandet"
    assert update_dto.category == "Kyrkogårdsförvaltning"

    status_calls = [c[0][2] for c in task_repo.update_status.call_args_list]
    assert status_calls[-1].status == "completed"

    publisher.publish.assert_called_once()


async def test_both_fail_all_none_still_completes() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    session, doc_repo, task_repo, publisher = _make_deps(task, doc)

    rule_extractor = MagicMock(return_value=MetadataResult())
    llm_extractor = AsyncMock(return_value=MetadataResult())

    await _call(
        doc.id,
        task.id,
        session,
        doc_repo,
        task_repo,
        publisher,
        rule_extractor,
        llm_extractor,
    )

    doc_repo.update.assert_called_once()
    _session, _doc_id, update_dto = doc_repo.update.call_args[0]
    assert update_dto.case_number is None
    assert update_dto.decision_date is None
    assert update_dto.decision_outcome is None
    assert update_dto.category is None

    status_calls = [c[0][2] for c in task_repo.update_status.call_args_list]
    assert status_calls[-1].status == "completed"

    publisher.publish.assert_called_once()


async def test_exception_during_processing_marks_task_failed() -> None:
    doc = _make_doc_read()
    task = _make_task_read(doc.id)
    session, doc_repo, task_repo, publisher = _make_deps(task, doc)

    doc_repo.update = AsyncMock(side_effect=RuntimeError("db write error"))
    rule_extractor = MagicMock(return_value=MetadataResult())
    llm_extractor = AsyncMock(return_value=MetadataResult())

    await _call(
        doc.id,
        task.id,
        session,
        doc_repo,
        task_repo,
        publisher,
        rule_extractor,
        llm_extractor,
    )

    session.rollback.assert_called_once()

    status_calls = [c[0][2] for c in task_repo.update_status.call_args_list]
    assert status_calls[-1].status == "failed"
    assert "db write error" in status_calls[-1].error_message

    publisher.publish.assert_not_called()
