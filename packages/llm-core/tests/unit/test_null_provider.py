"""The whole point of `NullProvider` is *when* it fails: never on construction,
always on use.
"""

from __future__ import annotations

import pytest

from llm_core import LLMDisabledError, LLMProvider
from llm_core._config import LLMConfig, ProviderKind, create_provider
from llm_core._types import Message, Role

_MESSAGES = [Message(role=Role.user, content="hej")]


def _null_provider(model: str = "unused-model") -> LLMProvider:
    return create_provider(LLMConfig(provider=ProviderKind.NONE, model=model))


def test_constructs_without_api_key_or_base_url() -> None:
    """The reason this kind exists: a process whose LLM steps are switched off
    starts normally instead of dying on a credential it will never use."""
    provider = _null_provider()

    assert isinstance(provider, LLMProvider)


def test_satisfies_the_provider_protocol() -> None:
    """It is handed to `generate()` and friends in place of a real provider, so
    a missing method would only surface at the call site."""
    provider = _null_provider()

    assert callable(provider.generate)
    assert callable(provider.generate_stream)


async def test_generate_refuses_and_names_the_model() -> None:
    provider = _null_provider("mistralai/Mistral-Small")

    with pytest.raises(LLMDisabledError) as excinfo:
        await provider.generate(_MESSAGES)

    assert "generate" in str(excinfo.value)
    assert "mistralai/Mistral-Small" in str(excinfo.value)


async def test_generate_stream_refuses_on_await_not_on_iteration() -> None:
    """Same shape as the real providers: a coroutine returning an iterator, so
    the refusal arrives before any `async for`, not part-way through one."""
    provider = _null_provider()

    with pytest.raises(LLMDisabledError):
        await provider.generate_stream(_MESSAGES)


def test_llm_provider_env_value_selects_it() -> None:
    """`LLM_PROVIDER=none` is the documented process-wide off switch."""
    assert ProviderKind("none") is ProviderKind.NONE
