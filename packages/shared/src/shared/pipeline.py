"""The shared task envelope that every pipeline worker runs inside.

Each worker consumes a task, does its unique work, and on success hands the
document to the next stage. The bookkeeping around that work — claiming the task,
marking it ``processing`` / ``completed`` / ``failed``, committing at the right
points, creating and publishing the next task, and rolling back on error — is
identical across workers. :func:`run_pipeline_step` owns that envelope so each
worker's ``process_*`` shrinks to "define the body, call the runner".

Failure handling distinguishes two kinds of error the body may raise:

- :class:`StepInputError` — the task's inputs are invalid (e.g. the document is
  missing or has no text). The body raises this *before* writing anything, so the
  task is marked ``failed`` without a rollback and the error is never re-raised;
  it is an expected, terminal outcome for that document.
- any other exception — an unexpected failure *during* the work. The session is
  rolled back, the task is marked ``failed``, and the exception is re-raised only
  when ``reraise=True`` (workers whose messages should be redelivered/retried).

Progress logging lives here for the same reason the bookkeeping does: every step
runs through this envelope, so one started/completed/failed pair here is the one
place that reports *every* stage at the same level of detail. A worker logs only
what is specific to its own work (how many chunks, how many characters) — if a
step is silent in a pipeline run, the envelope still says it ran and how long it
took.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.task import TaskCreate, TaskRead, TaskStatusUpdate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import TaskRepo

__all__ = ["StepInputError", "run_pipeline_step"]

logger = logging.getLogger(__name__)


def _handoff(next_step: PipelineStep | None) -> str:
    """How a completed step's log line ends: what it handed the document to."""
    return f" -> queued {next_step}" if next_step is not None else " (final step)"


async def _pending_next_task(
    session: AsyncSession,
    task_repo: TaskRepo,
    document_id: UUID,
    next_step: PipelineStep,
) -> TaskRead:
    """The next step's task, pending and ready to publish.

    `tasks` holds at most one row per (document, step), so handing a document on
    for the second time — a re-driven step, a redelivered message — has to reuse
    the row that is already there. Creating a second one violates
    `uq_tasks_document_id_step` and fails the step that had just succeeded.
    """
    existing = await task_repo.get_by_document_and_step(session, document_id, next_step)
    if existing is None:
        return await task_repo.create(
            session,
            TaskCreate(
                document_id=document_id,
                step=next_step,
                status=TaskStatus.PENDING,
            ),
        )

    reset = await task_repo.update_status(
        session, existing.id, TaskStatusUpdate(status=TaskStatus.PENDING)
    )
    # `existing` was just read inside this transaction, so the row is there.
    assert reset is not None
    return reset


class StepInputError(Exception):
    """Raised by a step body when the task's inputs are invalid.

    Signals an expected, terminal failure for the document: the envelope marks
    the task ``failed`` but does not roll back (nothing was written yet) and never
    re-raises.
    """


async def run_pipeline_step(
    *,
    task_repo: TaskRepo,
    session: AsyncSession,
    task_id: UUID,
    document_id: UUID,
    next_step: PipelineStep | None,
    queue_publisher: QueuePublisher | None = None,
    body: Callable[[], Awaitable[None]],
    reraise: bool = False,
) -> None:
    """Run one worker's ``body`` inside the shared task envelope.

    - Claims the task (skipping if it is missing or already completed) and marks
      it ``processing``.
    - Runs ``body`` (the worker's unique work).
    - On success: if ``next_step`` is set, creates the next pending task and
      publishes it to that step's topic, then marks this task ``completed``.
    - On :class:`StepInputError`: marks the task ``failed`` (no rollback, no
      re-raise).
    - On any other exception: rolls back, marks the task ``failed``, and re-raises
      when ``reraise`` is true.
    """
    task = await task_repo.get_by_id(session, task_id)
    if task is None:
        logger.info("Task %s not found, skipping", task_id)
        return
    if task.status == TaskStatus.COMPLETED:
        logger.info(
            "%s: document %s already completed, skipping", task.step, document_id
        )
        return

    logger.info("%s: document %s started", task.step, document_id)
    await task_repo.update_status(
        session, task_id, TaskStatusUpdate(status=TaskStatus.PROCESSING)
    )
    await session.commit()

    started_at = time.perf_counter()
    try:
        await body()

        if next_step is not None:
            # A publishing step must supply a publisher; a terminal step (embed)
            # passes next_step=None and no publisher.
            assert queue_publisher is not None, "next_step requires a queue_publisher"
            next_task = await _pending_next_task(
                session, task_repo, document_id, next_step
            )
            await session.commit()
            queue_publisher.publish(
                next_step,
                QueueMessage(task_id=next_task.id, document_id=document_id),
            )

        await task_repo.update_status(
            session, task_id, TaskStatusUpdate(status=TaskStatus.COMPLETED)
        )
        await session.commit()
        logger.info(
            "%s: document %s completed in %.1fs%s",
            task.step,
            document_id,
            time.perf_counter() - started_at,
            _handoff(next_step),
        )
    except StepInputError as exc:
        logger.info("%s: document %s rejected — %s", task.step, document_id, exc)
        await task_repo.update_status(
            session,
            task_id,
            TaskStatusUpdate(status=TaskStatus.FAILED, error_message=str(exc)),
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error(
            "%s: document %s failed after %.1fs — %s",
            task.step,
            document_id,
            time.perf_counter() - started_at,
            exc,
            exc_info=True,
        )
        await task_repo.update_status(
            session,
            task_id,
            TaskStatusUpdate(status=TaskStatus.FAILED, error_message=str(exc)),
        )
        await session.commit()
        if reraise:
            raise
