from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from worker_extract.extractors.factory import (
    ExtractStrategyMode,
    get_extraction_strategy,
)
from shared.segmentation import split_document
from worker_extract.extractors.llm import LLMStrategy
from worker_extract.extractors.rule_based import RuleBasedStrategy
from worker_extract.models import ExtractionResult


class TestStrategySelection:
    def test_strategy_rule_based_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXTRACT_STRATEGY", ExtractStrategyMode.RULE_BASED)
        strategy = get_extraction_strategy()
        assert isinstance(strategy, RuleBasedStrategy)

    def test_strategy_llm_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXTRACT_STRATEGY", ExtractStrategyMode.LLM)
        strategy = get_extraction_strategy()
        assert isinstance(strategy, LLMStrategy)

    def test_strategy_fallback_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "EXTRACT_STRATEGY", ExtractStrategyMode.RULE_BASED_WITH_LLM_FALLBACK
        )
        strategy = get_extraction_strategy()
        assert not isinstance(strategy, RuleBasedStrategy)
        assert not isinstance(strategy, LLMStrategy)

    def test_strategy_default_is_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EXTRACT_STRATEGY", raising=False)
        strategy = get_extraction_strategy()
        assert not isinstance(strategy, RuleBasedStrategy)
        assert not isinstance(strategy, LLMStrategy)

    def test_strategy_invalid_env_var_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EXTRACT_STRATEGY", "invalid_value")
        strategy = get_extraction_strategy()
        assert not isinstance(strategy, RuleBasedStrategy)
        assert not isinstance(strategy, LLMStrategy)


class TestStrategyExtract:
    async def test_rule_based_strategy_extract_returns_result(self) -> None:
        strategy = RuleBasedStrategy()
        result = await strategy.extract(
            split_document(
                "Kyrkoherden överklagade med hänvisning till ärende ÖN 2021-0345."
            )
        )
        assert isinstance(result, ExtractionResult)
        assert len(result.references) == 1

    async def test_llm_strategy_extract_calls_ai_service(self) -> None:
        from ai.dtos import EntityResult

        strategy = LLMStrategy()
        empty_result = EntityResult(entities=[], references=[])
        with patch(
            "worker_extract.extractors.llm.ai_extract_entities",
            AsyncMock(return_value=empty_result),
        ):
            result = await strategy.extract(
                split_document("Document text"), case_number="2023-0001"
            )
        assert isinstance(result, ExtractionResult)

    async def test_llm_strategy_passes_case_number_to_ai(self) -> None:
        from ai.dtos import EntityResult

        strategy = LLMStrategy()
        empty_result = EntityResult(entities=[], references=[])
        with patch(
            "worker_extract.extractors.llm.ai_extract_entities",
            AsyncMock(return_value=empty_result),
        ) as mock:
            await strategy.extract(
                split_document("Document text"), case_number="2023-0042"
            )
        # The LLM sees the body, never the appendices.
        mock.assert_called_once_with("Document text", "2023-0042", provider=None)
