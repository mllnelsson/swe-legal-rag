"""Measure text in the embedding model's own tokens.

The chunk worker has to decide how much text fits in one embedding. That is a
question about the embedding model's tokenizer, and nothing else: a general
purpose ruler such as tiktoken counts a different alphabet and answers a
different question. Measured on Swedish, cl100k runs roughly 1.37x the e5
tokenizer, so a budget kept in cl100k tokens is not conservative — it is simply
unrelated to the limit that decides truncation.

The window is *observed* from the tokenizer, never declared in config. The
embedding dimension is declared because a second artefact — the
`chunks.embedding` column — has to agree with it, and nothing else can reconcile
the two. The sequence window has no such counterpart: the tokenizer carries it,
so a declared copy could only ever disagree with the model.

`EMBEDDING_WINDOW_OVERRIDE` is the escape hatch for a process that cannot reach
the tokenizer at all: set it and none is loaded — the window is whatever the
variable says and counting falls back to a deliberately pessimistic
characters-per-token estimate. It is on whoever sets it to give the right number
for the model in use.

Counting convention: `count_tokens` returns *content* tokens, with no special
tokens included. A caller composing several pieces into one input adds
`SPECIAL_TOKEN_COUNT` once for the whole thing; counting specials per piece would
charge for them as many times as there are pieces.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from ai.errors import EmbeddingWindowError
from ai.llm_config import EmbeddingConfig, resolve_embedding_config

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizerBase

logger = logging.getLogger(__name__)

# The `<s>` and `</s>` an XLM-R style tokenizer wraps around every encoded input.
SPECIAL_TOKEN_COUNT = 2

# `transformers` reports `model_max_length` as `int(1e30)` when the tokenizer's
# config omits the field. Read unguarded that sentinel becomes an unlimited chunk
# budget, which is the failure this module exists to prevent — so any window at
# or above this floor is treated as "not observable" rather than as a number.
MODEL_MAX_LENGTH_SENTINEL_FLOOR = 1_000_000

# Characters per token assumed when running without a tokenizer. The densest
# Swedish text measured on real decisions is 0.5 tokens per character, so 2.0 is
# the worst case rather than the average (~3.5) — the estimate can then only run
# high, and a chunk budget built on it can only come out small. It costs roughly
# double the chunks, which is the price of not having the real tokenizer.
ESTIMATED_CHARS_PER_TOKEN = 2.0

type CountTokens = Callable[[str], int]

__all__ = [
    "SPECIAL_TOKEN_COUNT",
    "CountTokens",
    "EmbeddingRuler",
    "create_embedding_ruler",
    "verify_embedding_window",
]


@dataclass(frozen=True)
class EmbeddingRuler:
    """A token counter plus the window it is counting against.

    Deliberately a value carrying a callable rather than a Protocol with an
    implementation behind it: there is exactly one tokenizer, and what a caller
    varies is the counting function. Handing consumers this value also keeps
    `transformers` out of their tests — a fake is a lambda, so there is nothing
    to patch and no risk of importing torch into the unit suite.
    """

    count_tokens: CountTokens
    max_sequence_tokens: int


@lru_cache(maxsize=1)
def _load_tokenizer(model_name: str) -> PreTrainedTokenizerBase:
    """Load the tokenizer once per process.

    Cached because `scripts/run_pipeline.py` composes the chunk and embed workers
    into a single process, and each builds its own ruler.
    """
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_name)


def create_embedding_ruler(config: EmbeddingConfig | None = None) -> EmbeddingRuler:
    """Build the ruler for the configured embedding model.

    Resolves the config itself when not given, mirroring
    `create_embedding_provider`, so the ruler and the provider always describe
    the same model — including when `EMBEDDING_MODEL` overrides it.
    """
    if config is None:
        config = resolve_embedding_config()

    if config.window_override is not None:
        logger.warning(
            "EMBEDDING_WINDOW_OVERRIDE=%d: no tokenizer loaded. Chunk sizes are "
            "estimated at %.1f characters per token and the window is taken on "
            "trust — verify it matches %r.",
            config.window_override,
            ESTIMATED_CHARS_PER_TOKEN,
            config.model,
        )
        return EmbeddingRuler(
            count_tokens=_estimate_tokens,
            max_sequence_tokens=config.window_override,
        )

    tokenizer = _load_tokenizer(config.model)

    def count_tokens(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return EmbeddingRuler(
        count_tokens=count_tokens,
        max_sequence_tokens=_observe_window(tokenizer, config.model),
    )


def verify_embedding_window(ruler: EmbeddingRuler, *, reserved_tokens: int) -> int:
    """Check that the fixed overhead leaves room to embed anything.

    Call once at process startup. `reserved_tokens` is everything the caller adds
    around the text it is budgeting — prefixes, separators, special tokens — so
    what this really asserts is that a budget derived from the window is
    positive.

    Returns the observed window, which the caller threads downstream instead of
    re-reading a constant. Without it a window too small for the overhead
    surfaces as chunks silently truncated to nothing at embed time.
    """
    if reserved_tokens <= 0:
        raise EmbeddingWindowError(
            f"Reserved token count must be positive, got {reserved_tokens}. The "
            f"caller computes it from its own prefixes and separators, so a "
            f"non-positive value is a bug there, not in the model."
        )

    window = ruler.max_sequence_tokens
    if window >= MODEL_MAX_LENGTH_SENTINEL_FLOOR:
        raise EmbeddingWindowError(
            f"The embedding model reports a sequence window of {window}, which is "
            f"the sentinel transformers uses when `model_max_length` is missing "
            f"from the tokenizer config. The real window cannot be observed, and "
            f"guessing one would mean silently truncated embeddings."
        )
    if window <= 0:
        raise EmbeddingWindowError(
            f"The embedding model reports a sequence window of {window}. A "
            f"non-positive window leaves nothing to embed."
        )
    if reserved_tokens >= window:
        raise EmbeddingWindowError(
            f"Fixed overhead of {reserved_tokens} tokens leaves no room in the "
            f"model's {window}-token window. Reduce the summary reserve or the "
            f"prefixes before any text can be embedded."
        )
    return window


def _estimate_tokens(text: str) -> int:
    """Token count for a process running without the tokenizer.

    Rounds up, and assumes the densest text rather than the average, so it
    overestimates: what it can cause is chunks smaller than they needed to be,
    never a chunk that overruns the window.
    """
    return math.ceil(len(text) / ESTIMATED_CHARS_PER_TOKEN)


def _observe_window(tokenizer: PreTrainedTokenizerBase, model: str) -> int:
    """The tokenizer's declared maximum input length.

    Kept separate from the checks in `verify_embedding_window` so that building a
    ruler never raises: a bad window is reported once, at startup, by the
    invariant — not wherever a ruler happens to be constructed.
    """
    window: Any = getattr(tokenizer, "model_max_length", 0)
    if not isinstance(window, int):
        raise EmbeddingWindowError(
            f"Tokenizer for {model!r} reports a non-integer model_max_length: "
            f"{window!r}"
        )
    return window
