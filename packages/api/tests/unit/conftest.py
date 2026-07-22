from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _berget_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dummy credential so app startup can construct LLM providers.

    `api.main._lifespan` constructs real provider instances (fail-fast on a
    missing key, matching production). Constructing an `AsyncOpenAI` client
    makes no network calls by itself, and these unit tests mock `answer_query`
    (or higher), so a dummy key is enough — no real API traffic occurs.
    """
    monkeypatch.setenv("BERGET_API_KEY", "test-key")
