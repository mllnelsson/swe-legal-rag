"""Strategy selection and the strategies themselves.

These used to assert `isinstance(strategy, RuleBasedStrategy)`. With the
strategies as plain callables there is no class to name, which is just as well:
what matters is whether a mode reaches the model, not what type the object is.
Each test below distinguishes the modes by whether the LLM was called.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from ai.dtos import EntityResult
from shared.segmentation import split_document
from worker_extract.config import ExtractStrategyMode, get_extract_settings
from worker_extract.extractors.factory import create_extraction_strategy
from worker_extract.extractors.llm import extract_with_llm
from worker_extract.extractors.rule_based import extract_rule_based_strategy

# Text the regex pass finds nothing in, so the fallback mode must reach the LLM.
_NO_ENTITIES = "x" * 50

# Text the regex pass finds a reference in.
_WITH_REFERENCE = "Kyrkoherden överklagade med hänvisning till ärende ÖN 2021-0345."

_EMPTY = EntityResult(entities=[], references=[])


@pytest.fixture(autouse=True)
def _uncached_settings(monkeypatch: pytest.MonkeyPatch):
    """`get_extract_settings` is lru_cached, so the mode is read once per
    process. Tests that vary EXTRACT_STRATEGY have to drop the cache."""
    get_extract_settings.cache_clear()
    yield
    get_extract_settings.cache_clear()


@pytest.fixture
def no_provider(monkeypatch: pytest.MonkeyPatch):
    """The two LLM modes build a provider at selection time. Selection is what
    is under test here, not provider construction."""
    monkeypatch.setattr(
        "worker_extract.extractors.factory.create_llm_provider", lambda role: None
    )


class TestStrategySelection:
    async def test_rule_based_mode_never_calls_the_model(
        self, monkeypatch: pytest.MonkeyPatch, no_provider: None
    ) -> None:
        monkeypatch.setenv("EXTRACT_STRATEGY", ExtractStrategyMode.RULE_BASED)
        strategy = create_extraction_strategy()

        with patch(
            "worker_extract.extractors.llm.extract_entities", AsyncMock()
        ) as llm:
            await strategy(split_document(_NO_ENTITIES), None)

        llm.assert_not_called()

    async def test_llm_mode_always_calls_the_model(
        self, monkeypatch: pytest.MonkeyPatch, no_provider: None
    ) -> None:
        monkeypatch.setenv("EXTRACT_STRATEGY", ExtractStrategyMode.LLM)
        strategy = create_extraction_strategy()

        with patch(
            "worker_extract.extractors.llm.extract_entities",
            AsyncMock(return_value=_EMPTY),
        ) as llm:
            # Text the regex pass would have handled: the LLM mode asks anyway.
            await strategy(split_document(_WITH_REFERENCE), None)

        llm.assert_called_once()

    async def test_fallback_mode_calls_the_model_only_when_regex_comes_up_short(
        self, monkeypatch: pytest.MonkeyPatch, no_provider: None
    ) -> None:
        monkeypatch.setenv(
            "EXTRACT_STRATEGY", ExtractStrategyMode.RULE_BASED_WITH_LLM_FALLBACK
        )
        strategy = create_extraction_strategy()

        with patch(
            "worker_extract.extractors.llm.extract_entities",
            AsyncMock(return_value=_EMPTY),
        ) as llm:
            await strategy(split_document(_WITH_REFERENCE), None)
            assert llm.call_count == 0, "regex found entities; the model is not needed"

            await strategy(split_document(_NO_ENTITIES), None)
            assert llm.call_count == 1, "regex found nothing; the model fills in"

    async def test_default_mode_is_the_fallback(
        self, monkeypatch: pytest.MonkeyPatch, no_provider: None
    ) -> None:
        monkeypatch.delenv("EXTRACT_STRATEGY", raising=False)
        strategy = create_extraction_strategy()

        with patch(
            "worker_extract.extractors.llm.extract_entities",
            AsyncMock(return_value=_EMPTY),
        ) as llm:
            await strategy(split_document(_WITH_REFERENCE), None)
            assert llm.call_count == 0
            await strategy(split_document(_NO_ENTITIES), None)
            assert llm.call_count == 1

    def test_an_unrecognised_mode_is_fatal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """This used to fall back to the default without a word, so a typo in
        EXTRACT_STRATEGY silently ran a different extractor than the one asked
        for. Now the settings object refuses to build."""
        monkeypatch.setenv("EXTRACT_STRATEGY", "invalid_value")

        with pytest.raises(ValidationError, match="invalid_value"):
            create_extraction_strategy()


class TestStrategies:
    async def test_rule_based_extracts_references(self) -> None:
        result = await extract_rule_based_strategy(split_document(_WITH_REFERENCE))

        assert isinstance(result, EntityResult)
        assert len(result.references) == 1

    async def test_llm_sees_the_body_and_the_case_number(self) -> None:
        with patch(
            "worker_extract.extractors.llm.extract_entities",
            AsyncMock(return_value=_EMPTY),
        ) as mock:
            result = await extract_with_llm(
                split_document("Document text"), "2023-0042"
            )

        assert isinstance(result, EntityResult)
        # The LLM sees the body, never the appendices.
        mock.assert_called_once_with("Document text", "2023-0042", provider=None)
