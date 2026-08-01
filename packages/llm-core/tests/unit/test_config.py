"""`create_provider`'s dispatch is ours; `LLMConfig`'s env reading is
pydantic-settings. The Berget base URL asserted below lives nowhere else in the
codebase, which is the reason these patch-and-assert-called tests earn their
keep.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from llm_core._config import LLMConfig, create_provider


def test_create_provider_unknown_raises() -> None:
    with patch.dict("os.environ", {"LLM_PROVIDER": "openai"}):
        config = LLMConfig()
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(config)


def test_create_provider_gemini_returns_instance() -> None:
    mock_instance = MagicMock()
    with patch(
        "llm_core.providers._gemini.GeminiProvider", return_value=mock_instance
    ) as mock_cls:
        config = LLMConfig(provider="gemini")
        result = create_provider(config)
    mock_cls.assert_called_once_with(config)
    assert result is mock_instance


def test_create_provider_berget_returns_instance() -> None:
    mock_instance = MagicMock()
    with patch(
        "llm_core.providers._openai_compatible.OpenAiCompatibleProvider",
        return_value=mock_instance,
    ) as mock_cls:
        config = LLMConfig(provider="berget", berget_api_key="key")
        result = create_provider(config)
    mock_cls.assert_called_once_with(
        config, default_base_url="https://api.berget.ai/v1"
    )
    assert result is mock_instance


def test_create_provider_uses_default_config_when_none() -> None:
    mock_instance = MagicMock()
    with patch(
        "llm_core.providers._openai_compatible.OpenAiCompatibleProvider",
        return_value=mock_instance,
    ):
        result = create_provider(None)
    assert result is mock_instance
