"""Data-access layer: one module of functions per aggregate.

Each module (`document`, `task`, `chunk`, …) exposes async functions taking an
`AsyncSession` as the first argument and returning Pydantic DTOs — ORM objects never
escape this layer. Worker services receive these modules as injected namespaces typed by
the Protocols in `_protocols.py`; API code imports the modules directly.
"""

from shared.repositories import (
    chunk,
    document,
    document_entity,
    document_reference,
    entity,
    search,
    session,
    task,
    unresolved_reference,
)
from shared.repositories._protocols import (
    ChunkRepo,
    DocumentEntityRepo,
    DocumentReferenceRepo,
    DocumentRepo,
    EntityRepo,
    TaskRepo,
    UnresolvedReferenceRepo,
)

__all__ = [
    # repository modules
    "chunk",
    "document",
    "document_entity",
    "document_reference",
    "entity",
    "search",
    "session",
    "task",
    "unresolved_reference",
    # injection protocols
    "ChunkRepo",
    "DocumentEntityRepo",
    "DocumentReferenceRepo",
    "DocumentRepo",
    "EntityRepo",
    "TaskRepo",
    "UnresolvedReferenceRepo",
]
