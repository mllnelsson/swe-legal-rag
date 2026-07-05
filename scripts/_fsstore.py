"""JSON-on-filesystem repository fakes for the DB-free ingestion playground.

These let `scripts/run_step.py --store fs` run the real worker services without
Postgres. The services are dependency-injected and only ever touch the session
via ``commit()`` / ``rollback()`` (never a direct query), so swapping the
SQLAlchemy repositories for these file-backed ones is enough to make a whole
step — or the whole chain — run against JSON files instead of a database.

Design:
- ``FsStore`` holds every table in memory and (de)serializes each as a JSON list
  of the pydantic ``*Read`` DTOs (``model_dump(mode="json")``). PDFs are NOT here
  — they already live on disk via ``LocalStorageBackend``.
- ``FsSession`` mirrors the DB transaction boundary: ``commit()`` persists the
  in-memory rows to JSON, ``rollback()`` reloads them from JSON (discarding
  uncommitted mutations). This preserves rollback fidelity, e.g. a parser error
  rolls back the ``raw_text`` write exactly as Postgres would.
- Each ``Fs*Repository`` reproduces the method surface and dedup keys of its real
  counterpart in ``packages/shared/src/shared/repositories``.

This module is a dev tool: it is intentionally outside the uv workspace packages
and is never imported by production code.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from shared.dtos.chunk import ChunkCreate, ChunkRead
from shared.dtos.document import DocumentCreate, DocumentRead, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate, DocumentEntityRead
from shared.dtos.document_reference import DocumentReferenceCreate, DocumentReferenceRead
from shared.dtos.entity import EntityCreate, EntityRead
from shared.dtos.task import TaskCreate, TaskRead, TaskStatusUpdate
from shared.dtos.unresolved_reference import UnresolvedReferenceCreate, UnresolvedReferenceRead

_TERMINAL = {"completed", "failed"}

# table name -> DTO stored in that table's JSON file
TABLES: dict[str, type[BaseModel]] = {
    "documents": DocumentRead,
    "tasks": TaskRead,
    "chunks": ChunkRead,
    "entities": EntityRead,
    "document_entities": DocumentEntityRead,
    "references": DocumentReferenceRead,
    "unresolved": UnresolvedReferenceRead,
}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class FsStore:
    """In-memory tables backed by one JSON file per table under ``base_dir``."""

    def __init__(self, base_dir: Path) -> None:
        self._dir = Path(base_dir)
        self.rows: dict[str, list[Any]] = {table: [] for table in TABLES}
        self.reload()

    def _path(self, table: str) -> Path:
        return self._dir / f"{table}.json"

    def reload(self) -> None:
        """(Re)load every table from disk, discarding uncommitted in-memory rows."""
        for table, model in TABLES.items():
            path = self._path(table)
            if path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.rows[table] = [model.model_validate(item) for item in raw]
            else:
                self.rows[table] = []

    def persist(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        for table in TABLES:
            data = [row.model_dump(mode="json") for row in self.rows[table]]
            self._path(table).write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )


class FsSession:
    """Duck-typed AsyncSession: commit -> persist, rollback -> reload."""

    def __init__(self, store: FsStore) -> None:
        self._store = store

    async def commit(self) -> None:
        self._store.persist()

    async def rollback(self) -> None:
        self._store.reload()

    async def flush(self) -> None:
        return None


class FsDocumentRepository:
    def __init__(self, store: FsStore) -> None:
        self._store = store

    @property
    def _rows(self) -> list[DocumentRead]:
        return self._store.rows["documents"]

    async def create(self, dto: DocumentCreate) -> DocumentRead:
        now = _now()
        doc = DocumentRead(
            id=uuid4(),
            source_url=dto.source_url,
            gcs_uri=None,
            raw_text=None,
            summary=None,
            case_number=None,
            decision_date=None,
            decision_outcome=None,
            category=None,
            created_at=now,
            updated_at=now,
        )
        self._rows.append(doc)
        return doc

    async def get_by_id(self, document_id: UUID) -> DocumentRead | None:
        return next((d for d in self._rows if d.id == document_id), None)

    async def get_by_source_url(self, source_url: str) -> DocumentRead | None:
        return next((d for d in self._rows if d.source_url == source_url), None)

    async def get_by_case_number(self, case_number: str) -> DocumentRead | None:
        return next((d for d in self._rows if d.case_number == case_number), None)

    async def update(self, document_id: UUID, dto: DocumentUpdate) -> DocumentRead | None:
        rows = self._rows
        for i, doc in enumerate(rows):
            if doc.id == document_id:
                changes = dto.model_dump(exclude_none=True)
                changes["updated_at"] = _now()
                rows[i] = doc.model_copy(update=changes)
                return rows[i]
        return None


class FsTaskRepository:
    def __init__(self, store: FsStore) -> None:
        self._store = store

    @property
    def _rows(self) -> list[TaskRead]:
        return self._store.rows["tasks"]

    async def create(self, dto: TaskCreate) -> TaskRead:
        task = TaskRead(
            id=uuid4(),
            document_id=dto.document_id,
            step=dto.step,
            status=dto.status,
            error_message=None,
            started_at=None,
            completed_at=None,
        )
        self._rows.append(task)
        return task

    async def get_by_id(self, task_id: UUID) -> TaskRead | None:
        return next((t for t in self._rows if t.id == task_id), None)

    async def get_by_document_and_step(self, document_id: UUID, step: str) -> TaskRead | None:
        return next(
            (t for t in self._rows if t.document_id == document_id and t.step == step), None
        )

    async def update_status(
        self, task_id: UUID, status_update: TaskStatusUpdate
    ) -> TaskRead | None:
        rows = self._rows
        for i, task in enumerate(rows):
            if task.id == task_id:
                changes: dict[str, object] = {
                    "status": status_update.status,
                    "error_message": status_update.error_message,
                }
                if status_update.status == "processing":
                    changes["started_at"] = _now()
                elif status_update.status in _TERMINAL:
                    changes["completed_at"] = _now()
                rows[i] = task.model_copy(update=changes)
                return rows[i]
        return None

    # --- runner helpers (not part of the real repo; used for re-run prep) ---

    async def reset_to_pending(self, document_id: UUID, step: str) -> UUID:
        existing = await self.get_by_document_and_step(document_id, step)
        if existing is None:
            created = await self.create(TaskCreate(document_id=document_id, step=step))
            return created.id
        rows = self._rows
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

    async def delete_by_document_and_step(self, document_id: UUID, step: str) -> None:
        self._store.rows["tasks"] = [
            t for t in self._rows if not (t.document_id == document_id and t.step == step)
        ]


class FsChunkRepository:
    def __init__(self, store: FsStore) -> None:
        self._store = store

    @property
    def _rows(self) -> list[ChunkRead]:
        return self._store.rows["chunks"]

    async def bulk_create(self, dtos: list[ChunkCreate]) -> list[ChunkRead]:
        now = _now()
        created = [
            ChunkRead(
                id=uuid4(),
                document_id=dto.document_id,
                chunk_index=dto.chunk_index,
                chunk_text=dto.chunk_text,
                contextual_text=dto.contextual_text,
                embedding=dto.embedding,
                created_at=now,
            )
            for dto in dtos
        ]
        self._rows.extend(created)
        return created

    async def get_by_document_id(self, document_id: UUID) -> list[ChunkRead]:
        chunks = [c for c in self._rows if c.document_id == document_id]
        return sorted(chunks, key=lambda c: c.chunk_index)

    async def update_embeddings(self, updates: list[tuple[UUID, list[float]]]) -> None:
        by_id = dict(updates)
        rows = self._rows
        for i, chunk in enumerate(rows):
            if chunk.id in by_id:
                rows[i] = chunk.model_copy(update={"embedding": by_id[chunk.id]})

    async def delete_by_document_id(self, document_id: UUID) -> int:
        rows = self._rows
        keep = [c for c in rows if c.document_id != document_id]
        removed = len(rows) - len(keep)
        self._store.rows["chunks"] = keep
        return removed


class FsEntityRepository:
    def __init__(self, store: FsStore) -> None:
        self._store = store

    @property
    def _rows(self) -> list[EntityRead]:
        return self._store.rows["entities"]

    async def upsert(self, dto: EntityCreate) -> EntityRead:
        existing = next(
            (e for e in self._rows if e.name == dto.name and e.type == dto.type), None
        )
        if existing is not None:
            return existing
        entity = EntityRead(id=uuid4(), name=dto.name, type=dto.type, created_at=_now())
        self._rows.append(entity)
        return entity


class FsDocumentEntityRepository:
    def __init__(self, store: FsStore) -> None:
        self._store = store

    @property
    def _rows(self) -> list[DocumentEntityRead]:
        return self._store.rows["document_entities"]

    async def upsert(self, dto: DocumentEntityCreate) -> DocumentEntityRead:
        rows = self._rows
        for i, de in enumerate(rows):
            if de.document_id == dto.document_id and de.entity_id == dto.entity_id:
                if dto.relevance == "primary" and de.relevance != "primary":
                    rows[i] = de.model_copy(update={"relevance": "primary"})
                return rows[i]
        de = DocumentEntityRead(
            document_id=dto.document_id, entity_id=dto.entity_id, relevance=dto.relevance
        )
        rows.append(de)
        return de


class FsDocumentReferenceRepository:
    def __init__(self, store: FsStore) -> None:
        self._store = store

    @property
    def _rows(self) -> list[DocumentReferenceRead]:
        return self._store.rows["references"]

    async def upsert(self, dto: DocumentReferenceCreate) -> DocumentReferenceRead:
        existing = next(
            (
                r
                for r in self._rows
                if r.source_document_id == dto.source_document_id
                and r.target_document_id == dto.target_document_id
            ),
            None,
        )
        if existing is not None:
            return existing
        ref = DocumentReferenceRead(
            source_document_id=dto.source_document_id,
            target_document_id=dto.target_document_id,
            reference_context=dto.reference_context,
        )
        self._rows.append(ref)
        return ref


class FsUnresolvedReferenceRepository:
    def __init__(self, store: FsStore) -> None:
        self._store = store

    @property
    def _rows(self) -> list[UnresolvedReferenceRead]:
        return self._store.rows["unresolved"]

    async def upsert(self, dto: UnresolvedReferenceCreate) -> UnresolvedReferenceRead:
        existing = next(
            (
                r
                for r in self._rows
                if r.source_document_id == dto.source_document_id
                and r.target_case_number == dto.target_case_number
            ),
            None,
        )
        if existing is not None:
            return existing
        ref = UnresolvedReferenceRead(
            id=uuid4(),
            source_document_id=dto.source_document_id,
            target_case_number=dto.target_case_number,
            reference_context=dto.reference_context,
            created_at=_now(),
        )
        self._rows.append(ref)
        return ref

    async def get_by_target_case_number(self, case_number: str) -> list[UnresolvedReferenceRead]:
        return [r for r in self._rows if r.target_case_number == case_number]

    async def delete(self, ref_id: UUID) -> None:
        self._store.rows["unresolved"] = [r for r in self._rows if r.id != ref_id]
