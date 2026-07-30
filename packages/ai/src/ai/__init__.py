from llm_core import trace_context

from ai._observability import LLMTraceConfig, install_file_tracing
from ai._pricing import ModelPrice, estimate_cost_usd, find_model_price
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
from ai.errors import AiError, EmbeddingDimensionMismatchError
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
    # Cost is priced at read time from the model and tokens in a trace record,
    # never frozen into it — see ai/_pricing.py and scripts/llm_cost.py.
    "estimate_cost_usd",
    "find_model_price",
    "ModelPrice",
    # Service functions
    "decompose_query",
    "extract_metadata",
    "extract_entities",
    "summarize_document",
    "synthesize_answer",
    # Embedding
    "EmbeddingProvider",
    "EmbeddingConfig",
    "create_embedding_provider",
    "verify_embedding_dimension",
    # Errors
    "AiError",
    "EmbeddingDimensionMismatchError",
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
