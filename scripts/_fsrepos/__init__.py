"""File-backed repository namespaces mirroring ``shared.repositories``.

Each module exposes the same functions as its real counterpart (taking an
``AsyncSession`` first, which is really an :class:`~_fsstore.FsSession`) so it can be
injected into the worker services in place of the SQLAlchemy repositories. Dev-only.
"""

from _fsrepos import (
    chunk,
    document,
    document_entity,
    document_reference,
    entity,
    task,
    unresolved_reference,
)

__all__ = [
    "chunk",
    "document",
    "document_entity",
    "document_reference",
    "entity",
    "task",
    "unresolved_reference",
]
