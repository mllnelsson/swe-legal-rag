"""`create_provider`'s dispatch is ours; `LLMConfig`'s env reading is
pydantic-settings.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from llm_core._config import LLMConfig, ProviderKind, create_provider


def test_unknown_provider_is_rejected_when_the_config_is_built() -> None:
    """`provider` is a ProviderKind, so a bad value fails at the point it was
    supplied rather than later at dispatch. `create_provider` has no fallback
    case precisely because this cannot get past here."""
    with patch.dict("os.environ", {"LLM_PROVIDER": "openai"}):
        with pytest.raises(ValidationError):
            LLMConfig()


def test_create_provider_openai_compatible_returns_instance() -> None:
    mock_instance = MagicMock()
    with patch(
        "llm_core.providers._openai_compatible.OpenAiCompatibleProvider",
        return_value=mock_instance,
    ) as mock_cls:
        config = LLMConfig(provider=ProviderKind.OPENAI_COMPATIBLE, api_key="key")
        result = create_provider(config)
    mock_cls.assert_called_once_with(config)
    assert result is mock_instance


def test_create_provider_gemini_returns_instance() -> None:
    mock_instance = MagicMock()
    with patch(
        "llm_core.providers._gemini.GeminiProvider", return_value=mock_instance
    ) as mock_cls:
        config = LLMConfig(provider=ProviderKind.GEMINI)
        result = create_provider(config)
    mock_cls.assert_called_once_with(config)
    assert result is mock_instance


def test_create_provider_uses_default_config_when_none() -> None:
    mock_instance = MagicMock()
    with patch(
        "llm_core.providers._openai_compatible.OpenAiCompatibleProvider",
        return_value=mock_instance,
    ):
        result = create_provider(None)
    assert result is mock_instance
