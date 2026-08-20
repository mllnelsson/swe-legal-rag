"""Domain errors for the ai package."""

from __future__ import annotations


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


class LLMConfigError(AiError):
    """Base class for problems with `llm_config.yaml`."""


class LLMConfigNotFoundError(LLMConfigError):
    """No `llm_config.yaml` could be located.

    Deliberately fatal rather than falling back to built-in defaults: a silent
    fallback is how the documented model set and the one actually in use drift
    apart, which has already happened once in this project.
    """


class LLMConfigInvalidError(LLMConfigError):
    """`llm_config.yaml` was found but is malformed or internally inconsistent."""


class UnknownLLMRoleError(LLMConfigError):
    """A provider was requested for a role that `llm_config.yaml` does not declare."""
