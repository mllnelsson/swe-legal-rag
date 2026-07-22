from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from llm_core._config import LLMConfig, create_provider


def test_llmconfig_defaults() -> None:
    config = LLMConfig()
    assert config.provider == "berget"
    assert config.model == "gemini-2.0-flash"
    assert config.temperature == 0.0
    assert config.max_tokens is None
    assert config.gemini_api_key is None
    assert config.berget_api_key is None
    assert config.base_url is None


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


def test_llmconfig_reads_berget_env_vars() -> None:
    env = {
        "LLM_PROVIDER": "berget",
        "LLM_MODEL": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
        "BERGET_API_KEY": "my-berget-key",
        "LLM_BASE_URL": "https://example.test/v1",
    }
    with patch.dict("os.environ", env):
        config = LLMConfig()
    assert config.provider == "berget"
    assert config.model == "mistralai/Mistral-Small-3.2-24B-Instruct-2506"
    assert config.berget_api_key == "my-berget-key"
    assert config.base_url == "https://example.test/v1"


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
