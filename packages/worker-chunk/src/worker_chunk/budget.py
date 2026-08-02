"""Derive the chunk token budget from the embedding model's sequence window.

What the embed worker actually sends the model is

    passage_prefix + summary + CONTEXTUAL_SEPARATOR + chunk_text

wrapped in the tokenizer's special tokens. Every one of those pieces spends the
same 512-token window, so the budget left for chunk text is the window minus all
of them. Chunking to a budget that ignores the summary is how chunk tails end up
silently truncated at embed time, which is the bug this module exists to close.

Worked example for e5-large, which is what the numbers below were sized against:

    window                                    512
    special tokens                              2   SPECIAL_TOKEN_COUNT
    "passage: "                                 2   measured, not assumed
    summary reserve                           150   SUMMARY_RESERVE_TOKENS
    "\\n\\n---\\n\\n"                             1   measured, not assumed
    safety margin                               8   SAFETY_MARGIN_TOKENS
                                             ----
    chunk budget                              349
    overlap                                    34   OVERLAP_FRACTION of the budget

The prefix and separator are measured with the real ruler rather than hard-coded:
`passage_prefix` is configuration and is `""` for a model with no prefixes, and
the separator is a chunker constant. A hard-coded 2 and 1 would mis-budget the
moment either moves.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ai import SPECIAL_TOKEN_COUNT
from worker_chunk.errors import ChunkBudgetError

# Room set aside for the document summary that is prepended to every chunk. The
# two summaries measured on real decisions came to 110 and 143 tokens, so this
# clears them untouched: truncation is a backstop for a model that ignores its
# instructions, not routine mutilation of well-behaved output.
SUMMARY_RESERVE_TOKENS = 150

# Absorbs the difference between counting the pieces separately and encoding them
# as one string. They agree exactly on the inputs measured here; the margin is
# there so that a tokenizer which merges across a boundary cannot overrun.
SAFETY_MARGIN_TOKENS = 8

# Overlap as a share of the budget rather than an absolute, so it stays sensible
# when the window or the reserve move. At a 349-token budget it lands on 34.
OVERLAP_FRACTION = 0.10


class ChunkBudget(BaseModel):
    """How many tokens each part of a contextual passage may spend."""

    model_config = ConfigDict(frozen=True)

    max_tokens: int
    overlap_tokens: int
    summary_reserve_tokens: int


def fixed_overhead_tokens(*, prefix_tokens: int, separator_tokens: int) -> int:
    """Everything in a contextual passage that is not chunk text.

    Its own function so that the startup invariant and the budget are given the
    identical number rather than two expressions that have to be kept in step.
    """
    return (
        SPECIAL_TOKEN_COUNT
        + prefix_tokens
        + separator_tokens
        + SUMMARY_RESERVE_TOKENS
        + SAFETY_MARGIN_TOKENS
    )


def compute_chunk_budget(
    *, window_tokens: int, prefix_tokens: int, separator_tokens: int
) -> ChunkBudget:
    """Split the model's window between the summary and the chunk text."""
    max_tokens = window_tokens - fixed_overhead_tokens(
        prefix_tokens=prefix_tokens, separator_tokens=separator_tokens
    )
    if max_tokens <= 0:
        raise ChunkBudgetError(
            f"A {window_tokens}-token embedding window leaves {max_tokens} tokens "
            f"for chunk text once the {SUMMARY_RESERVE_TOKENS}-token summary "
            f"reserve, the prefixes and the margin are taken. Lower the reserve "
            f"or use a model with a longer window."
        )

    return ChunkBudget(
        max_tokens=max_tokens,
        overlap_tokens=int(max_tokens * OVERLAP_FRACTION),
        summary_reserve_tokens=SUMMARY_RESERVE_TOKENS,
    )
