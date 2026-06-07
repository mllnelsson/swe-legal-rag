from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.document import Document
from shared.models.task import Task
from shared.queue.base import QueueMessage
from shared.queue.sync import SyncQueuePublisher
from shared.repositories.document import DocumentRepository
from shared.repositories.task import TaskRepository
from worker_metadata.patterns import MetadataResult, extract_metadata_rule_based
from worker_metadata.service import process_metadata


@pytest.mark.integration
async def test_metadata_flow_populates_fields_and_completes_task(
    session: AsyncSession,
    document_repo: DocumentRepository,
    task_repo: TaskRepository,
    sync_publisher: SyncQueuePublisher,
    published_messages: list[QueueMessage],
    test_document,
    metadata_task,
) -> None:
    llm_extractor = AsyncMock(return_value=MetadataResult())

    await process_metadata(
        document_id=test_document.id,
        task_id=metadata_task.id,
        document_repo=document_repo,
        task_repo=task_repo,
        queue_publisher=sync_publisher,
        rule_extractor=extract_metadata_rule_based,
        llm_extractor=llm_extractor,
        session=session,
        next_topic="extract",
    )

    doc_row = (
        await session.execute(select(Document).where(Document.id == test_document.id))
    ).scalar_one()
    assert doc_row.case_number == "2023-0042"
    assert doc_row.decision_date == datetime.date(2023, 1, 15)
    assert doc_row.decision_outcome is not None
    assert "bifaller" in doc_row.decision_outcome
    assert doc_row.category == "Kyrkogårdsförvaltning"

    task_row = (
        await session.execute(select(Task).where(Task.id == metadata_task.id))
    ).scalar_one()
    assert task_row.status == "completed"
    assert task_row.completed_at is not None

    assert len(published_messages) == 1
    assert published_messages[0].document_id == test_document.id

    llm_extractor.assert_not_called()
