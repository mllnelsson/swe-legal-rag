"""Finite-set domain vocabularies shared across the system.

These are ``StrEnum`` so each member *is* the exact string already stored in the
database and passed on the queue. That has a deliberate consequence: DB columns
stay ``Mapped[str]`` and **no migration is needed** to adopt these enums — they
are applied at the DTO / business-logic boundary, where they turn stringly-typed
comparisons into explicit, matchable options.
"""

from enum import StrEnum, auto

__all__ = [
    "TaskStatus",
    "PipelineStep",
    "EntityType",
    "EntityRelevance",
    "ChunkSection",
]


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
    """Category of a legal entity extracted from a document.

    ``KEYWORD`` differs in provenance from the rest: the other members are
    *inferred* from the decision's prose by regex or LLM, while a keyword is
    *declared* by Överklagandenämnden itself on the trailer's ``Sökord:`` line.
    That makes it the one type the corpus vouches for, and the reason extraction
    reads it deterministically rather than through a strategy.
    """

    LEGAL_CONCEPT = auto()
    ROLE = auto()
    PARISH = auto()
    REGULATION = auto()
    KEYWORD = auto()


class EntityRelevance(StrEnum):
    """How central an entity is to the document it was found in."""

    PRIMARY = auto()
    MENTIONED = auto()


class ChunkSection(StrEnum):
    """Which part of the source PDF a chunk was cut from.

    Decision PDFs carry the appealed decision as an appendix, so an ``APPENDIX``
    chunk holds the *lower instance's* words — often the reasoning Överklagande-
    nämnden went on to overturn. Retrieval defaults to ``BODY`` for that reason.
    """

    BODY = auto()
    APPENDIX = auto()
