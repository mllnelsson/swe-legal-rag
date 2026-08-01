"""Driving pipeline steps the way a rerun really happens.

Kept out of the test files because getting this wrong looks like it works: a test
that models a rerun as a second `TaskCreate` for the same document and step is
writing a row the `uq_tasks_document_id_step` constraint forbids.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.task import TaskStatusUpdate
from shared.enums import TaskStatus

__all__ = ["redrive_task"]


async def redrive_task(
    session: AsyncSession, task_repo: Any, task_id: uuid.UUID
) -> None:
    """Reset a finished task to pending so its step can be run a second time.

    A rerun is the same task row driven again. `tasks` holds at most one row per
    (document, step), and `run_pipeline_step` skips a task it finds already
    completed — so pending is the state a re-drive has to restore.
    """
    await task_repo.update_status(
        session, task_id, TaskStatusUpdate(status=TaskStatus.PENDING)
    )
    await session.commit()
