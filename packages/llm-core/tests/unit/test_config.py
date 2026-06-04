from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from llm_core._config import LLMConfig, create_provider


def test_llmconfig_defaults() -> None:
    config = LLMConfig()
    assert config.provider == "gemini"
    assert config.model == "gemini-2.0-flash"
    assert config.temperature == 0.0
    assert config.max_tokens is None
    assert config.gemini_api_key is None


def test_llmconfig_reads_env_vars() -> None:
    env = {
        "LLM_PROVIDER": "gemini",
        "LLM_MODEL": "gemini-1.5-pro",
        "LLM_TEMPERATURE": "0.7",
        "LLM_MAX_TOKENS": "1000",
        "GEMINI_API_KEY": "my-test-key",
    }
    with patch.dict("os.environ", env):
        config = LLMConfig()
    assert config.provider == "gemini"
    assert config.model == "gemini-1.5-pro"
    assert config.temperature == 0.7
    assert config.max_tokens == 1000
    assert config.gemini_api_key == "my-test-key"


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
        config = LLMConfig()
        result = create_provider(config)
    mock_cls.assert_called_once_with(config)
    assert result is mock_instance


def test_create_provider_uses_default_config_when_none() -> None:
    mock_instance = MagicMock()
    with patch("llm_core.providers._gemini.GeminiProvider", return_value=mock_instance):
        result = create_provider(None)
    assert result is mock_instance
