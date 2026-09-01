from __future__ import annotations

import logging
from functools import partial

from ai.dtos import EntityResult, ExtractedReference
from ai.providers.roles import LLMRole, create_llm_provider, llm_role_is_disabled
from agent_kit.llm import LLMDisabledError
from shared.segmentation import DocumentSegments
from worker_extract.config import ExtractStrategyMode, get_extract_settings
from worker_extract.entities import deduplicate_entities
from worker_extract.extractors.base import ExtractionStrategy
from worker_extract.extractors.llm import extract_with_llm
from worker_extract.extractors.rule_based import extract_rule_based_strategy

logger = logging.getLogger(__name__)

# How much body text the regex pass is expected to yield one entity from. Below
# that rate the pass is treated as having missed, and the LLM is asked as well.
_CHARS_PER_ENTITY_ESTIMATE = 1000


def _is_result_complete(result: EntityResult, segments: DocumentSegments) -> bool:
    # Sized against the body alone: the yardstick is how much of the nämnd's own
    # text there is to extract from, and appendix length says nothing about that.
    if not result.entities:
        return False
    min_expected = max(1, len(segments.body) // _CHARS_PER_ENTITY_ESTIMATE)
    return len(result.entities) >= min_expected


def _merge_results(primary: EntityResult, fallback: EntityResult) -> EntityResult:
    ref_map: dict[str, ExtractedReference] = {}
    for ref in primary.references + fallback.references:
        if ref.case_number not in ref_map:
            ref_map[ref.case_number] = ref

    return EntityResult(
        entities=deduplicate_entities(primary.entities + fallback.entities),
        references=list(ref_map.values()),
    )


async def _extract_rule_based_then_llm(
    segments: DocumentSegments,
    case_number: str | None = None,
    *,
    llm: ExtractionStrategy,
) -> EntityResult:
    """Try the regex pass, and only pay for the model when it comes up short."""
    result = await extract_rule_based_strategy(segments, case_number)
    if _is_result_complete(result, segments):
        return result
    return _merge_results(result, await llm(segments, case_number))


def create_extraction_strategy() -> ExtractionStrategy:
    """Build the strategy `EXTRACT_STRATEGY` selects.

    Call once per process, not once per document: two of the three modes
    construct an LLM provider, and every other worker builds its provider at
    startup and injects it.
    """
    mode = get_extract_settings().extract_strategy
    if llm_role_is_disabled(LLMRole.STRUCTURED):
        return _strategy_without_llm(mode)

    match mode:
        case ExtractStrategyMode.RULE_BASED:
            return extract_rule_based_strategy
        case ExtractStrategyMode.LLM:
            return partial(
                extract_with_llm, provider=create_llm_provider(LLMRole.STRUCTURED)
            )
        case ExtractStrategyMode.RULE_BASED_WITH_LLM_FALLBACK:
            return partial(
                _extract_rule_based_then_llm,
                llm=partial(
                    extract_with_llm,
                    provider=create_llm_provider(LLMRole.STRUCTURED),
                ),
            )


def _strategy_without_llm(mode: ExtractStrategyMode) -> ExtractionStrategy:
    """What each mode becomes when the `structured` role is `kind: none`.

    The fallback mode degrades to its regex half: it already treats the model as
    optional, and an off switch you have to remember to set twice is not an off
    switch. `LLM` refuses instead — it was asked for explicitly, and silently
    running the regex pass would be running something the operator did not ask
    for, on a step whose output nothing downstream re-checks.
    """
    match mode:
        case ExtractStrategyMode.RULE_BASED:
            return extract_rule_based_strategy
        case ExtractStrategyMode.RULE_BASED_WITH_LLM_FALLBACK:
            logger.warning(
                "Role %r is configured as %r, so EXTRACT_STRATEGY=%s runs its "
                "rule-based half only; entities the regex pass misses stay missed.",
                LLMRole.STRUCTURED.value,
                "none",
                mode.value,
            )
            return extract_rule_based_strategy
        case ExtractStrategyMode.LLM:
            raise LLMDisabledError(
                f"EXTRACT_STRATEGY={mode.value} needs a model, but the "
                f"{LLMRole.STRUCTURED.value!r} role resolves to a provider of "
                f"kind 'none'. Use EXTRACT_STRATEGY="
                f"{ExtractStrategyMode.RULE_BASED.value}, or point the role at a "
                f"real provider."
            )
