"""JSON-on-filesystem store + session for the DB-free ingestion playground.

These let `scripts/run_step.py --store fs` run the real worker services without
Postgres. The services are dependency-injected and only ever touch the session
via ``commit()`` / ``rollback()`` (never a direct query), so swapping the
SQLAlchemy repository namespaces for the file-backed ones in ``_fsrepos`` is
enough to make a whole step — or the whole chain — run against JSON files
instead of a database.

Design:
- ``FsStore`` holds every table in memory and (de)serializes each as a JSON list
  of the pydantic ``*Read`` DTOs (``model_dump(mode="json")``). PDFs are NOT here
  — they already live on disk via ``LocalStorageBackend``.
- ``FsSession`` mirrors the DB transaction boundary: ``commit()`` persists the
  in-memory rows to JSON, ``rollback()`` reloads them from JSON (discarding
  uncommitted mutations). This preserves rollback fidelity, e.g. a parser error
  rolls back the ``raw_text`` write exactly as Postgres would. It exposes the
  backing ``store`` so the ``_fsrepos`` functions can reach the rows: the service
  hands the session (cast to ``AsyncSession``) to each repo function, and the fs
  functions recover the store via :func:`store_of`.
- The ``_fsrepos`` modules reproduce the method surface and dedup keys of the real
  repositories in ``packages/shared/src/shared/repositories``.

This module is a dev tool: it is intentionally outside the uv workspace packages
and is never imported by production code.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.chunk import ChunkRead
from shared.dtos.document import DocumentRead
from shared.dtos.document_entity import DocumentEntityRead
from shared.dtos.document_reference import DocumentReferenceRead
from shared.dtos.entity import EntityRead
from shared.dtos.task import TaskRead
from shared.dtos.unresolved_reference import UnresolvedReferenceRead

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


def now() -> datetime:
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
        self.store = store

    async def commit(self) -> None:
        self.store.persist()

    async def rollback(self) -> None:
        self.store.reload()

    async def flush(self) -> None:
        return None


def store_of(session: AsyncSession) -> FsStore:
    """Recover the backing :class:`FsStore` from a session handed to an fs repo.

    ``run_step.py`` casts the :class:`FsSession` to ``AsyncSession`` for injection,
    so the fs repo functions cast it back here to reach the in-memory rows.
    """
    return cast(FsSession, session).store
