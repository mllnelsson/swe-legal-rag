from llm_core import trace_context

from ai._observability import LLMTraceConfig, install_file_tracing
from ai.dtos import (
    ChunkContext,
    DateFilter,
    DecomposeRequest,
    DecomposeResult,
    EmbedRequest,
    EmbedResult,
    EntityRequest,
    EntityResult,
    ExtractedEntity,
    ExtractedReference,
    MetadataRequest,
    MetadataResult,
    SourceCitation,
    SummarizeRequest,
    SummarizeResult,
    SynthesizeRequest,
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
    LLMConfigError,
    LLMConfigInvalidError,
    LLMConfigNotFoundError,
    UnknownLLMRoleError,
)
from ai.llm_config import (
    LLMConfigDocument,
    get_embedding_prefixes,
    get_llm_config,
    resolve_embedding_config,
    resolve_role_config,
)
from ai.providers.roles import (
    ROLE_CHAT,
    ROLE_STRUCTURED,
    ROLE_SUMMARIZE,
    create_chat_llm_provider,
    create_llm_provider,
    create_structured_llm_provider,
    create_summarize_llm_provider,
)
from ai.services import (
    decompose_query,
    extract_entities,
    extract_metadata,
    summarize_document,
    synthesize_answer,
)

__all__ = [
    # Observability. Every process making LLM calls installs tracing once at
    # startup and sets trace_context at each unit-of-work boundary.
    "install_file_tracing",
    "LLMTraceConfig",
    "trace_context",
    # Service functions
    "decompose_query",
    "extract_metadata",
    "extract_entities",
    "summarize_document",
    "synthesize_answer",
    # Per-task model assignment, resolved from llm_config.yaml. A role is a
    # name declared in that file; the three constants are the ones with call
    # sites, not the whole set.
    "create_llm_provider",
    "create_structured_llm_provider",
    "create_summarize_llm_provider",
    "create_chat_llm_provider",
    "ROLE_STRUCTURED",
    "ROLE_SUMMARIZE",
    "ROLE_CHAT",
    # Configuration
    "LLMConfigDocument",
    "get_llm_config",
    "resolve_role_config",
    "resolve_embedding_config",
    "get_embedding_prefixes",
    # Embedding
    "EmbeddingProvider",
    "EmbeddingConfig",
    "create_embedding_provider",
    "verify_embedding_dimension",
    # Errors
    "AiError",
    "EmbeddingDimensionMismatchError",
    "LLMConfigError",
    "LLMConfigNotFoundError",
    "LLMConfigInvalidError",
    "UnknownLLMRoleError",
    # DTOs
    "DateFilter",
    "DecomposeRequest",
    "DecomposeResult",
    "ChunkContext",
    "SynthesizeRequest",
    "SourceCitation",
    "MetadataRequest",
    "MetadataResult",
    "EntityRequest",
    "EntityResult",
    "ExtractedEntity",
    "ExtractedReference",
    "SummarizeRequest",
    "SummarizeResult",
    "EmbedRequest",
    "EmbedResult",
]
