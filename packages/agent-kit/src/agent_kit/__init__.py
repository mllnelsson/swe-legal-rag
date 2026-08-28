"""Domain-free agent core: the generic machinery behind a conversational agent.

What lives here is everything a plan-then-execute-then-synthesize agent needs
that is not specific to any one corpus or language: the prompt renderer, the
LLM role/provider config, the file trace recorder and correlation scopes, the
per-conversation context store, the streaming synthesis step, and the
orchestrator that ties the three phases together.

It depends only on `llm-core` (the provider abstraction and the tool loop) plus
pydantic and pyyaml. It imports nothing from `shared`, `ai` or `agents` — the
domain lives there and consumes this, never the other way round.
"""

from __future__ import annotations

from agent_kit.config import (
    LLMConfigDocument,
    create_llm_provider,
    get_llm_config,
    llm_role_is_disabled,
    load_config_document,
    resolve_role_config,
    role_model_env_var,
)
from agent_kit.context import ContextStore, InMemoryContextStore, JsonBlob
from agent_kit.errors import (
    AgentKitError,
    LLMConfigError,
    LLMConfigInvalidError,
    LLMConfigNotFoundError,
    UnknownLLMRoleError,
)
from agent_kit.orchestrator import (
    AgentEvent,
    AgentRequest,
    DoneEvent,
    ErrorEvent,
    EvidenceEvent,
    ExecutionPhase,
    PlanPhase,
    PlanReplyEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolStatus,
    run_agent,
)
from agent_kit.prompts import PromptTemplate, render, render_tool_index
from agent_kit.synthesis import synthesize
from agent_kit.tracing import (
    FileTraceRecorder,
    LLMTraceConfig,
    agent_run_scope,
    install_file_tracing,
    interaction_scope,
    serialize_record,
)

__all__ = [
    # Prompt rendering.
    "PromptTemplate",
    "render",
    "render_tool_index",
    # Streaming answer synthesis.
    "synthesize",
    # The generic plan → execute → synthesize orchestrator and its events.
    "run_agent",
    "AgentRequest",
    "PlanPhase",
    "ExecutionPhase",
    "AgentEvent",
    "PlanReplyEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "EvidenceEvent",
    "TokenEvent",
    "DoneEvent",
    "ErrorEvent",
    "ToolStatus",
    # Per-conversation carry-over.
    "ContextStore",
    "InMemoryContextStore",
    "JsonBlob",
    # LLM role/provider config.
    "LLMConfigDocument",
    "create_llm_provider",
    "get_llm_config",
    "llm_role_is_disabled",
    "load_config_document",
    "resolve_role_config",
    "role_model_env_var",
    # Observability.
    "install_file_tracing",
    "FileTraceRecorder",
    "LLMTraceConfig",
    "serialize_record",
    "interaction_scope",
    "agent_run_scope",
    # Errors.
    "AgentKitError",
    "LLMConfigError",
    "LLMConfigNotFoundError",
    "LLMConfigInvalidError",
    "UnknownLLMRoleError",
]
