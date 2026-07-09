from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from _fsstore import now, store_of
from shared.dtos.task import TaskCreate, TaskRead, TaskStatusUpdate

_TERMINAL = {"completed", "failed"}


def _rows(session: AsyncSession) -> list[TaskRead]:
    return store_of(session).rows["tasks"]


async def create(session: AsyncSession, dto: TaskCreate) -> TaskRead:
    task = TaskRead(
        id=uuid4(),
        document_id=dto.document_id,
        step=dto.step,
        status=dto.status,
        error_message=None,
        started_at=None,
        completed_at=None,
    )
    _rows(session).append(task)
    return task


async def get_by_id(session: AsyncSession, task_id: UUID) -> TaskRead | None:
    return next((t for t in _rows(session) if t.id == task_id), None)


async def get_by_document_and_step(
    session: AsyncSession, document_id: UUID, step: str
) -> TaskRead | None:
    return next(
        (t for t in _rows(session) if t.document_id == document_id and t.step == step),
        None,
    )


async def update_status(
    session: AsyncSession, task_id: UUID, status_update: TaskStatusUpdate
) -> TaskRead | None:
    rows = _rows(session)
    for i, task in enumerate(rows):
        if task.id == task_id:
            changes: dict[str, object] = {
                "status": status_update.status,
                "error_message": status_update.error_message,
            }
            if status_update.status == "processing":
                changes["started_at"] = now()
            elif status_update.status in _TERMINAL:
                changes["completed_at"] = now()
            rows[i] = task.model_copy(update=changes)
            return rows[i]
    return None


# --- runner helpers (not part of the real repo; used by run_step for re-run prep) ---


async def reset_to_pending(session: AsyncSession, document_id: UUID, step: str) -> UUID:
    existing = await get_by_document_and_step(session, document_id, step)
    if existing is None:
        created = await create(session, TaskCreate(document_id=document_id, step=step))
        return created.id
    rows = _rows(session)
    for i, task in enumerate(rows):
        if task.id == existing.id:
            rows[i] = task.model_copy(
                update={
                    "status": "pending",
                    "error_message": None,
                    "started_at": None,
                    "completed_at": None,
                }
            )
            return rows[i].id
    return existing.id


async def delete_by_document_and_step(
    session: AsyncSession, document_id: UUID, step: str
) -> None:
    store = store_of(session)
    store.rows["tasks"] = [
        t
        for t in store.rows["tasks"]
        if not (t.document_id == document_id and t.step == step)
    ]
