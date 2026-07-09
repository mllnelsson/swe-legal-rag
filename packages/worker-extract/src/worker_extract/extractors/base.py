from __future__ import annotations

from typing import Protocol

from worker_extract.models import ExtractionResult


class ExtractionStrategy(Protocol):
    async def extract(
        self, document_text: str, case_number: str | None = None
    ) -> ExtractionResult: ...
