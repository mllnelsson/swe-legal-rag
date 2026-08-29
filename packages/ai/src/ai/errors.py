"""Domain errors for the ai package.

The LLM-config error family (`LLMConfigError` and friends) is re-exported from
`agent_kit.errors`: the config loader moved to the agent core, and its errors
moved with it. They are kept importable from `ai.errors` so existing call sites
and tests are unaffected. They subclass `agent_kit.errors.AgentKitError`, not
`AiError` — nothing catches `AiError` to reach them.
"""

from __future__ import annotations

from agent_kit.errors import (
    LLMConfigError,
    LLMConfigInvalidError,
    LLMConfigNotFoundError,
    UnknownLLMRoleError,
)

__all__ = [
    "AiError",
    "EmbeddingDimensionMismatchError",
    "EmbeddingWindowError",
    "TokenizerUnavailableError",
    "UnsupportedEmbeddingBackendError",
    "MissingApiKeyError",
    "LLMConfigError",
    "LLMConfigNotFoundError",
    "LLMConfigInvalidError",
    "UnknownLLMRoleError",
]


class AiError(Exception):
    """Base class for all ai package errors."""


class EmbeddingDimensionMismatchError(AiError):
    """The embedding model's output width disagrees with the configured dimension.

    Raised at startup rather than at embed time. The dimension is defined in four
    uncoordinated places (`llm_config.yaml`, `shared.config`, the Alembic migration,
    and implicitly the configured model); without this check a mismatch only surfaces
    after the pipeline has already done its expensive work, or as a failed user query
    on the API.
    """


class EmbeddingWindowError(AiError):
    """The embedding model's sequence window is unusable or cannot be observed.

    Raised at startup rather than at embed time. The window is declared nowhere —
    it is read off the tokenizer — so this is the only place a model whose
    tokenizer config omits `model_max_length`, or whose window is too small for
    the fixed overhead, can be caught. Text that overruns the window is truncated
    silently by the embedding model, which is why an unobservable window must
    stop the process instead of being guessed at.
    """


class TokenizerUnavailableError(AiError):
    """`transformers` could not build a tokenizer for the configured model.

    `AutoTokenizer.from_pretrained` is typed as returning `None` for a name it
    cannot resolve to a tokenizer class. Unguarded, that `None` travels as far as
    the first `count_tokens` call and surfaces as an `AttributeError` naming
    neither the model nor the config key that chose it — at which point the chunk
    worker has already started. Raised at ruler construction instead, where the
    model name is still in hand.

    `EMBEDDING_WINDOW_OVERRIDE` is the way past it for a process that genuinely
    cannot reach a tokenizer; see :mod:`ai.tokenization`.
    """


class UnsupportedEmbeddingBackendError(AiError):
    """`embedding.provider` names a host whose kind has no embeddings client.

    Raised while resolving the config, not at dispatch, so the message can name
    the YAML key at fault.
    """


class MissingApiKeyError(AiError):
    """An embedding provider was constructed without the API key it needs."""
