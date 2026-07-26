from __future__ import annotations

from typing import Protocol

from shared.segmentation import DocumentSegments
from worker_extract.models import ExtractionResult


class ExtractionStrategy(Protocol):
    """Extract entities and references from an already-segmented decision.

    Strategies take :class:`DocumentSegments` rather than raw text so each can
    decide what the appendices mean to it — the rule-based one scans them for
    entities but never for references, the LLM one ignores them entirely.
    """

    async def extract(
        self, segments: DocumentSegments, case_number: str | None = None
    ) -> ExtractionResult: ...
