from __future__ import annotations

import os
from enum import StrEnum, auto

from ai.providers.roles import create_structured_llm_provider
from worker_extract.entities import deduplicate_entities
from worker_extract.extractors.base import ExtractionStrategy
from worker_extract.extractors.llm import LLMStrategy
from worker_extract.extractors.rule_based import RuleBasedStrategy
from worker_extract.models import (
    ExtractionResult,
    ExtractedReference,
)

_CHARS_PER_ENTITY_ESTIMATE = 1000
_ENTITY_COUNT_PER_ESTIMATE_BLOCK = 1
_DEFAULT_STRATEGY_VALUE = "rule_based_with_llm_fallback"


class ExtractStrategyMode(StrEnum):
    RULE_BASED = auto()
    LLM = auto()
    RULE_BASED_WITH_LLM_FALLBACK = auto()


def _is_result_complete(result: ExtractionResult, document_text: str) -> bool:
    if not result.entities:
        return False
    min_expected = max(
        1,
        len(document_text)
        // _CHARS_PER_ENTITY_ESTIMATE
        * _ENTITY_COUNT_PER_ESTIMATE_BLOCK,
    )
    return len(result.entities) >= min_expected


def _merge_results(
    primary: ExtractionResult, fallback: ExtractionResult
) -> ExtractionResult:
    ref_map: dict[str, ExtractedReference] = {}
    for ref in primary.references + fallback.references:
        if ref.case_number not in ref_map:
            ref_map[ref.case_number] = ref

    return ExtractionResult(
        entities=deduplicate_entities(primary.entities + fallback.entities),
        references=list(ref_map.values()),
    )


class _FallbackStrategy:
    def __init__(self) -> None:
        self._rule_based = RuleBasedStrategy()
        self._llm = LLMStrategy(create_structured_llm_provider())

    async def extract(
        self, document_text: str, case_number: str | None = None
    ) -> ExtractionResult:
        result = await self._rule_based.extract(document_text, case_number)
        if _is_result_complete(result, document_text):
            return result
        llm_result = await self._llm.extract(document_text, case_number)
        return _merge_results(result, llm_result)


def get_extraction_strategy() -> ExtractionStrategy:
    mode_str = os.environ.get("EXTRACT_STRATEGY", _DEFAULT_STRATEGY_VALUE)
    try:
        mode = ExtractStrategyMode(mode_str)
    except ValueError:
        mode = ExtractStrategyMode.RULE_BASED_WITH_LLM_FALLBACK

    match mode:
        case ExtractStrategyMode.RULE_BASED:
            return RuleBasedStrategy()
        case ExtractStrategyMode.LLM:
            return LLMStrategy(create_structured_llm_provider())
        case ExtractStrategyMode.RULE_BASED_WITH_LLM_FALLBACK:
            return _FallbackStrategy()
