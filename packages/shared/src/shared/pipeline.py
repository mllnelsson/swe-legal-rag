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
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.task import TaskCreate, TaskStatusUpdate
from shared.enums import PipelineStep, TaskStatus
from shared.queue.base import QueueMessage, QueuePublisher
from shared.repositories import TaskRepo

__all__ = ["StepInputError", "run_pipeline_step"]

logger = logging.getLogger(__name__)


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
    if task is None or task.status == TaskStatus.COMPLETED:
        logger.info("Task %s already completed or not found, skipping", task_id)
        return

    await task_repo.update_status(
        session, task_id, TaskStatusUpdate(status=TaskStatus.PROCESSING)
    )
    await session.commit()

    try:
        await body()

        if next_step is not None:
            # A publishing step must supply a publisher; a terminal step (embed)
            # passes next_step=None and no publisher.
            assert queue_publisher is not None, "next_step requires a queue_publisher"
            next_task = await task_repo.create(
                session,
                TaskCreate(
                    document_id=document_id,
                    step=next_step,
                    status=TaskStatus.PENDING,
                ),
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
    except StepInputError as exc:
        logger.info("Task %s failed input validation: %s", task_id, exc)
        await task_repo.update_status(
            session,
            task_id,
            TaskStatusUpdate(status=TaskStatus.FAILED, error_message=str(exc)),
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error(
            "Pipeline step failed for task %s (document %s): %s",
            task_id,
            document_id,
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
