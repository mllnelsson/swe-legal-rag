from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _berget_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dummy credential so strategy selection can construct LLM providers.

    `get_extraction_strategy()` constructs a real provider instance for the
    LLM/fallback strategies (fail-fast on a missing key, matching production).
    Constructing an `AsyncOpenAI` client makes no network calls by itself,
    and these tests mock `ai_extract_entities` before any real call happens.
    """
    monkeypatch.setenv("BERGET_API_KEY", "test-key")
