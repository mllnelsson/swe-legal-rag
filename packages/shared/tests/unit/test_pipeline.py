"""Handing a document to the next step, first time and every time after.

`tasks` holds at most one row per (document, step). A step that succeeds twice —
re-driven by hand, or reached again by a redelivered message — must therefore
reuse the next-step row it created the first time. Creating a second one raises
`uq_tasks_document_id_step` and fails the step that had just succeeded.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

from shared.dtos.task import TaskRead
from shared.enums import PipelineStep, TaskStatus
from shared.pipeline import run_pipeline_step


def _make_task(step: str, status: str) -> TaskRead:
    return TaskRead(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        step=step,
        status=status,
        error_message=None,
        started_at=None,
        completed_at=None,
    )


def _make_task_repo(current: TaskRead, existing_next: TaskRead | None) -> MagicMock:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=current)
    repo.get_by_document_and_step = AsyncMock(return_value=existing_next)
    repo.create = AsyncMock(return_value=_make_task("embed", "pending"))
    repo.update_status = AsyncMock(side_effect=lambda _s, _id, _u: existing_next)
    return repo


async def _run(task_repo: MagicMock, publisher: MagicMock, current: TaskRead) -> None:
    await run_pipeline_step(
        session=AsyncMock(),
        task_repo=task_repo,
        task_id=current.id,
        document_id=current.document_id,
        body=AsyncMock(),
        next_step=PipelineStep.EMBED,
        queue_publisher=publisher,
    )


async def test_first_run_creates_the_next_task():
    current = _make_task("chunk", "pending")
    task_repo = _make_task_repo(current, existing_next=None)
    publisher = MagicMock()

    await _run(task_repo, publisher, current)

    task_repo.create.assert_called_once()
    publisher.publish.assert_called_once()


async def test_rerun_reuses_the_existing_next_task_instead_of_creating_a_second():
    current = _make_task("chunk", "pending")
    already_there = _make_task("embed", "completed")
    task_repo = _make_task_repo(current, existing_next=already_there)
    publisher = MagicMock()

    await _run(task_repo, publisher, current)

    task_repo.create.assert_not_called()
    published_message = publisher.publish.call_args.args[1]
    assert published_message.task_id == already_there.id


async def test_rerun_returns_the_reused_next_task_to_pending():
    """A next task left `completed` would be skipped by its own worker."""
    current = _make_task("chunk", "pending")
    already_there = _make_task("embed", "completed")
    task_repo = _make_task_repo(current, existing_next=already_there)

    await _run(task_repo, MagicMock(), current)

    statuses = [call.args[2].status for call in task_repo.update_status.call_args_list]
    assert TaskStatus.PENDING in statuses


async def test_completed_task_is_skipped_entirely():
    current = _make_task("chunk", "completed")
    task_repo = _make_task_repo(current, existing_next=None)
    publisher = MagicMock()

    await _run(task_repo, publisher, current)

    task_repo.create.assert_not_called()
    publisher.publish.assert_not_called()
