import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.task import TaskCreate, TaskRead, TaskStatusUpdate
from shared.models.task import Task

_PROCESSING = "processing"
_TERMINAL = {"completed", "failed"}


async def create(session: AsyncSession, dto: TaskCreate) -> TaskRead:
    task = Task(document_id=dto.document_id, step=dto.step, status=dto.status)
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return TaskRead.model_validate(task)


async def get_by_id(session: AsyncSession, task_id: uuid.UUID) -> TaskRead | None:
    task = await session.get(Task, task_id)
    return TaskRead.model_validate(task) if task else None


async def get_by_document_and_step(
    session: AsyncSession, document_id: uuid.UUID, step: str
) -> TaskRead | None:
    result = await session.execute(
        select(Task).where(Task.document_id == document_id, Task.step == step)
    )
    task = result.scalar_one_or_none()
    return TaskRead.model_validate(task) if task else None


async def update_status(
    session: AsyncSession, task_id: uuid.UUID, status_update: TaskStatusUpdate
) -> TaskRead | None:
    task = await session.get(Task, task_id)
    if task is None:
        return None
    now = datetime.now(tz=timezone.utc)
    task.status = status_update.status
    task.error_message = status_update.error_message
    if status_update.status == _PROCESSING:
        task.started_at = now
    elif status_update.status in _TERMINAL:
        task.completed_at = now
    await session.flush()
    await session.refresh(task)
    return TaskRead.model_validate(task)


async def list_by_step_and_status(
    session: AsyncSession, step: str, status: str
) -> list[TaskRead]:
    result = await session.execute(
        select(Task).where(Task.step == step, Task.status == status)
    )
    return [TaskRead.model_validate(row) for row in result.scalars()]
