"""Unit tests for the chunk token budget derived from the embedding window."""

from __future__ import annotations

import pytest

from ai import SPECIAL_TOKEN_COUNT
from worker_chunk.budget import (
    OVERLAP_FRACTION,
    SAFETY_MARGIN_TOKENS,
    SUMMARY_RESERVE_TOKENS,
    compute_chunk_budget,
    fixed_overhead_tokens,
)
from worker_chunk.errors import ChunkBudgetError

# e5-large's window and what "passage: " and "\n\n---\n\n" measure in its
# tokenizer — the configuration this project actually runs.
E5_WINDOW = 512
E5_PREFIX_TOKENS = 2
E5_SEPARATOR_TOKENS = 1


def test_budget_for_the_configured_model() -> None:
    budget = compute_chunk_budget(
        window_tokens=E5_WINDOW,
        prefix_tokens=E5_PREFIX_TOKENS,
        separator_tokens=E5_SEPARATOR_TOKENS,
    )

    assert budget.max_tokens == 349
    assert budget.overlap_tokens == 34
    assert budget.summary_reserve_tokens == SUMMARY_RESERVE_TOKENS


def test_every_token_of_the_window_is_accounted_for() -> None:
    budget = compute_chunk_budget(
        window_tokens=E5_WINDOW,
        prefix_tokens=E5_PREFIX_TOKENS,
        separator_tokens=E5_SEPARATOR_TOKENS,
    )

    spent = (
        SPECIAL_TOKEN_COUNT
        + E5_PREFIX_TOKENS
        + budget.summary_reserve_tokens
        + E5_SEPARATOR_TOKENS
        + budget.max_tokens
        + SAFETY_MARGIN_TOKENS
    )
    assert spent == E5_WINDOW


def test_a_model_without_prefixes_gets_those_tokens_back() -> None:
    with_prefix = compute_chunk_budget(
        window_tokens=E5_WINDOW,
        prefix_tokens=E5_PREFIX_TOKENS,
        separator_tokens=E5_SEPARATOR_TOKENS,
    )
    without_prefix = compute_chunk_budget(
        window_tokens=E5_WINDOW,
        prefix_tokens=0,
        separator_tokens=E5_SEPARATOR_TOKENS,
    )

    assert without_prefix.max_tokens == with_prefix.max_tokens + E5_PREFIX_TOKENS


def test_overlap_is_a_share_of_the_budget() -> None:
    budget = compute_chunk_budget(
        window_tokens=1024, prefix_tokens=2, separator_tokens=1
    )

    assert budget.overlap_tokens == int(budget.max_tokens * OVERLAP_FRACTION)
    assert budget.overlap_tokens < budget.max_tokens


def test_raises_when_the_window_cannot_hold_the_overhead() -> None:
    overhead = fixed_overhead_tokens(prefix_tokens=2, separator_tokens=1)

    with pytest.raises(ChunkBudgetError, match="leaves"):
        compute_chunk_budget(
            window_tokens=overhead, prefix_tokens=2, separator_tokens=1
        )
