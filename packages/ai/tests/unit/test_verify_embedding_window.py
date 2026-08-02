"""Unit tests for the startup embedding-window check."""

from __future__ import annotations

import pytest

from ai.errors import EmbeddingWindowError
from ai.tokenization import (
    MODEL_MAX_LENGTH_SENTINEL_FLOOR,
    EmbeddingRuler,
    verify_embedding_window,
)

WINDOW = 512


def _ruler(window: int) -> EmbeddingRuler:
    return EmbeddingRuler(
        count_tokens=lambda text: len(text.split()), max_sequence_tokens=window
    )


def test_returns_observed_window_when_overhead_fits() -> None:
    assert verify_embedding_window(_ruler(WINDOW), reserved_tokens=163) == WINDOW


def test_raises_when_reserved_tokens_is_not_positive() -> None:
    with pytest.raises(EmbeddingWindowError, match="must be positive"):
        verify_embedding_window(_ruler(WINDOW), reserved_tokens=0)


def test_raises_on_the_missing_model_max_length_sentinel() -> None:
    # transformers reports int(1e30) when the tokenizer config omits the field.
    # Accepting it would mean an unbounded chunk budget and silent truncation.
    sentinel = MODEL_MAX_LENGTH_SENTINEL_FLOOR

    with pytest.raises(EmbeddingWindowError, match="model_max_length"):
        verify_embedding_window(_ruler(sentinel), reserved_tokens=163)


def test_raises_when_window_is_not_positive() -> None:
    with pytest.raises(EmbeddingWindowError, match="nothing to embed"):
        verify_embedding_window(_ruler(0), reserved_tokens=163)


def test_raises_when_overhead_fills_the_whole_window() -> None:
    with pytest.raises(EmbeddingWindowError, match="no room"):
        verify_embedding_window(_ruler(WINDOW), reserved_tokens=WINDOW)


def test_accepts_an_overhead_one_token_under_the_window() -> None:
    assert verify_embedding_window(_ruler(WINDOW), reserved_tokens=WINDOW - 1) == WINDOW
