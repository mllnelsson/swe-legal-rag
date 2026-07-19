"""Finite-set domain vocabularies shared across the system.

These are ``StrEnum`` so each member *is* the exact string already stored in the
database and passed on the queue. That has a deliberate consequence: DB columns
stay ``Mapped[str]`` and **no migration is needed** to adopt these enums — they
are applied at the DTO / business-logic boundary, where they turn stringly-typed
comparisons into explicit, matchable options.
"""

from enum import StrEnum, auto

__all__ = ["TaskStatus", "PipelineStep", "EntityType", "EntityRelevance"]


class TaskStatus(StrEnum):
    """Lifecycle state of a single pipeline task."""

    PENDING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    FAILED = auto()


class PipelineStep(StrEnum):
    """One stage of the ingestion pipeline. The member name doubles as the queue
    topic the stage consumes from."""

    CRAWL = auto()
    DOWNLOAD = auto()
    PARSE = auto()
    METADATA = auto()
    EXTRACT = auto()
    CHUNK = auto()
    EMBED = auto()


class EntityType(StrEnum):
    """Category of a legal entity extracted from a document."""

    LEGAL_CONCEPT = auto()
    ROLE = auto()
    PARISH = auto()
    REGULATION = auto()


class EntityRelevance(StrEnum):
    """How central an entity is to the document it was found in."""

    PRIMARY = auto()
    MENTIONED = auto()
