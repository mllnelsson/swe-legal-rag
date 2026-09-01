from __future__ import annotations

from ai import extract_entities
from ai.dtos import EntityResult
from agent_kit.llm import LLMProvider
from shared.segmentation import DocumentSegments


async def extract_with_llm(
    segments: DocumentSegments,
    case_number: str | None = None,
    *,
    provider: LLMProvider | None = None,
) -> EntityResult:
    """Ask the model for entities and references in one call.

    Body only. The appendix is the appealed decision written in the same
    register, and the model has no way to tell whose reasoning is whose once the
    two are concatenated.

    `ai.dtos` already types the result's entity type and relevance as the shared
    enums, so the structured output is validated to the vocabulary at parse
    time. There is nothing left to map.
    """
    return await extract_entities(segments.body, case_number, provider=provider)
