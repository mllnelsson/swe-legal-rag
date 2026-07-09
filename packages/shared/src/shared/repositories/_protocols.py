"""Structural interfaces for the repository namespaces injected into worker services.

Worker services are handed a repo *namespace* (a module of functions) rather than a
session-bound object, so they can run against either the real SQLAlchemy repositories
(`shared.repositories.<name>`) or the JSON-file doubles used by
`scripts/run_step.py --store fs`. Both satisfy these Protocols structurally.

Members are declared as read-only `@property` returning a `Callable` rather than as
methods. This is deliberate: a module of module-level functions must satisfy the
Protocol, and both type checkers used here agree only on this form — pyright accepts a
module against method-style *and* property-style protocols, but ty accepts a module only
against the property style (a method member's unbound `self` is not stripped for a
module). Callers invoke the functions positionally, so the loss of parameter names on the
`Callable` is immaterial. Only the methods workers actually call are declared here
(interface segregation) — the fs doubles mirror exactly this surface.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.chunk import ChunkCreate, ChunkRead
from shared.dtos.document import DocumentCreate, DocumentRead, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate, DocumentEntityRead
from shared.dtos.document_reference import (
    DocumentReferenceCreate,
    DocumentReferenceRead,
)
from shared.dtos.entity import EntityCreate, EntityRead
from shared.dtos.task import TaskCreate, TaskRead, TaskStatusUpdate
from shared.dtos.unresolved_reference import (
    UnresolvedReferenceCreate,
    UnresolvedReferenceRead,
)


class DocumentRepo(Protocol):
    @property
    def create(
        self,
    ) -> Callable[[AsyncSession, DocumentCreate], Awaitable[DocumentRead]]: ...
    @property
    def get_by_id(
        self,
    ) -> Callable[[AsyncSession, uuid.UUID], Awaitable[DocumentRead | None]]: ...
    @property
    def get_by_source_url(
        self,
    ) -> Callable[[AsyncSession, str], Awaitable[DocumentRead | None]]: ...
    @property
    def get_by_case_number(
        self,
    ) -> Callable[[AsyncSession, str], Awaitable[DocumentRead | None]]: ...
    @property
    def update(
        self,
    ) -> Callable[
        [AsyncSession, uuid.UUID, DocumentUpdate], Awaitable[DocumentRead | None]
    ]: ...


class TaskRepo(Protocol):
    @property
    def create(self) -> Callable[[AsyncSession, TaskCreate], Awaitable[TaskRead]]: ...
    @property
    def get_by_id(
        self,
    ) -> Callable[[AsyncSession, uuid.UUID], Awaitable[TaskRead | None]]: ...
    @property
    def get_by_document_and_step(
        self,
    ) -> Callable[[AsyncSession, uuid.UUID, str], Awaitable[TaskRead | None]]: ...
    @property
    def update_status(
        self,
    ) -> Callable[
        [AsyncSession, uuid.UUID, TaskStatusUpdate], Awaitable[TaskRead | None]
    ]: ...


class ChunkRepo(Protocol):
    @property
    def bulk_create(
        self,
    ) -> Callable[[AsyncSession, list[ChunkCreate]], Awaitable[list[ChunkRead]]]: ...
    @property
    def get_by_document_id(
        self,
    ) -> Callable[[AsyncSession, uuid.UUID], Awaitable[list[ChunkRead]]]: ...
    @property
    def update_embeddings(
        self,
    ) -> Callable[
        [AsyncSession, list[tuple[uuid.UUID, list[float]]]], Awaitable[None]
    ]: ...
    @property
    def delete_by_document_id(
        self,
    ) -> Callable[[AsyncSession, uuid.UUID], Awaitable[int]]: ...


class EntityRepo(Protocol):
    @property
    def upsert(
        self,
    ) -> Callable[[AsyncSession, EntityCreate], Awaitable[EntityRead]]: ...


class DocumentEntityRepo(Protocol):
    @property
    def upsert(
        self,
    ) -> Callable[
        [AsyncSession, DocumentEntityCreate], Awaitable[DocumentEntityRead]
    ]: ...


class DocumentReferenceRepo(Protocol):
    @property
    def upsert(
        self,
    ) -> Callable[
        [AsyncSession, DocumentReferenceCreate], Awaitable[DocumentReferenceRead]
    ]: ...


class UnresolvedReferenceRepo(Protocol):
    @property
    def upsert(
        self,
    ) -> Callable[
        [AsyncSession, UnresolvedReferenceCreate], Awaitable[UnresolvedReferenceRead]
    ]: ...
    @property
    def get_by_target_case_number(
        self,
    ) -> Callable[[AsyncSession, str], Awaitable[list[UnresolvedReferenceRead]]]: ...
    @property
    def delete(self) -> Callable[[AsyncSession, uuid.UUID], Awaitable[None]]: ...
