from __future__ import annotations

from collections.abc import Awaitable, Callable

from ai.dtos import EntityResult
from shared.segmentation import DocumentSegments

__all__ = ["ExtractionStrategy"]

# How entities and references are pulled out of an already-segmented decision.
#
# A plain callable rather than a Protocol: the interface is one method, so a
# class adds a name and an instantiation and nothing else. The rule-based
# strategy is a module-level function; the two that need an LLM provider are
# built with `functools.partial`.
#
# Strategies take `DocumentSegments` rather than raw text so each can decide
# what the appendices mean to it — the rule-based one scans them for entities
# but never for references, the LLM one ignores them entirely.
type ExtractionStrategy = Callable[
    [DocumentSegments, str | None], Awaitable[EntityResult]
]
