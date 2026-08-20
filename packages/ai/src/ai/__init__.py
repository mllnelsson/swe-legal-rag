from llm_core import trace_context

from ai._observability import LLMTraceConfig, install_file_tracing
from ai._tracing_scope import agent_run_scope, interaction_scope
from ai.dtos import (
    ChunkContext,
    DecisionReading,
    DateFilter,
    DecomposeRequest,
    DecomposeResult,
    DirectReplyRequest,
    EmbedRequest,
    EmbedResult,
    EntityRequest,
    EntityResult,
    ExtractedEntity,
    ExtractedReference,
    MetadataRequest,
    MetadataResult,
    QueryExpansionRequest,
    QueryExpansionResult,
    SourceCitation,
    SummarizeRequest,
    SummarizeResult,
    SynthesizeRequest,
    TabularEvidence,
)
from ai.embedding import (
    EmbeddingConfig,
    EmbeddingProvider,
    create_embedding_provider,
    verify_embedding_dimension,
)
from ai.errors import (
    AiError,
    EmbeddingDimensionMismatchError,
    EmbeddingWindowError,
    LLMConfigError,
    LLMConfigInvalidError,
    LLMConfigNotFoundError,
    MissingApiKeyError,
    TokenizerUnavailableError,
    UnknownLLMRoleError,
    UnsupportedEmbeddingBackendError,
)
from ai.llm_config import (
    EmbeddingBackend,
    LLMConfigDocument,
    get_embedding_prefixes,
    get_llm_config,
    resolve_embedding_config,
    resolve_role_config,
)
from ai.providers.roles import LLMRole, create_llm_provider, llm_role_is_disabled
from ai.services import (
    decompose_query,
    expand_query,
    extract_entities,
    extract_metadata,
    reply_from_context,
    summarize_document,
    synthesize_answer,
)
from ai.tokenization import (
    SPECIAL_TOKEN_COUNT,
    CountTokens,
    EmbeddingRuler,
    create_embedding_ruler,
    verify_embedding_window,
)
from ai.worker import close_llm_clients, worker_trace_scope

__all__ = [
    # Observability. Every process making LLM calls installs tracing once at
    # startup and sets trace_context at each unit-of-work boundary.
    "install_file_tracing",
    "LLMTraceConfig",
    "trace_context",
    "worker_trace_scope",
    # Correlation. `interaction_scope` inherits an enclosing interaction id so a
    # sub-agent joins its caller's turn; `agent_run_scope` always mints, which
    # is what tells two invocations of one sub-agent apart inside that turn.
    "interaction_scope",
    "agent_run_scope",
    "close_llm_clients",
    # Service functions
    "decompose_query",
    "expand_query",
    "extract_metadata",
    "extract_entities",
    "summarize_document",
    "synthesize_answer",
    "reply_from_context",
    # Per-task model assignment. A role is an LLMRole member plus a matching
    # entry under `roles:` in llm_config.yaml; both halves are required.
    "create_llm_provider",
    "LLMRole",
    "llm_role_is_disabled",
    # Configuration
    "LLMConfigDocument",
    "EmbeddingBackend",
    "get_llm_config",
    "resolve_role_config",
    "resolve_embedding_config",
    "get_embedding_prefixes",
    # Embedding
    "EmbeddingProvider",
    "EmbeddingConfig",
    "create_embedding_provider",
    "verify_embedding_dimension",
    # Token budgeting. Text is measured with the embedding model's own tokenizer,
    # and the sequence window is observed from it rather than declared.
    "CountTokens",
    "EmbeddingRuler",
    "SPECIAL_TOKEN_COUNT",
    "create_embedding_ruler",
    "verify_embedding_window",
    # Errors
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
    # DTOs
    "DateFilter",
    "DecomposeRequest",
    "DecomposeResult",
    "ChunkContext",
    "DecisionReading",
    "DirectReplyRequest",
    "SynthesizeRequest",
    "TabularEvidence",
    "SourceCitation",
    "MetadataRequest",
    "MetadataResult",
    "QueryExpansionRequest",
    "QueryExpansionResult",
    "EntityRequest",
    "EntityResult",
    "ExtractedEntity",
    "ExtractedReference",
    "SummarizeRequest",
    "SummarizeResult",
    "EmbedRequest",
    "EmbedResult",
]
