from llm_core._clients import aclose_async_openai, get_async_openai
from llm_core._config import LLMConfig, ProviderKind, create_provider
from llm_core._exceptions import (
    LLMDisabledError,
    LLMError,
    MaxIterationsError,
    MissingCredentialError,
    ProviderError,
    ToolExecutionError,
)
from llm_core._protocol import LLMProvider
from llm_core._service import (
    ToolCallFinished,
    ToolCallStarted,
    ToolExecutor,
    ToolLoopEvent,
    ToolLoopFinished,
    ToolLoopResult,
    generate,
    generate_stream,
    generate_structured,
    run_tool_loop,
    tool_loop,
)
from llm_core._tracing import (
    LLMCallRecord,
    LLMOperation,
    TraceRecorder,
    current_trace_context,
    get_trace_recorder,
    set_trace_recorder,
    trace_context,
    trace_outcome,
    traced_call,
)
from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)
from llm_core.scratchpad import Handle, Preview, Scratchpad

__all__ = [
    "LLMConfig",
    "ProviderKind",
    "create_provider",
    "LLMProvider",
    "Message",
    "Role",
    "ToolCall",
    "ToolDefinition",
    "LLMResponse",
    "StreamChunk",
    "Usage",
    "LLMOperation",
    "LLMCallRecord",
    "TraceRecorder",
    "set_trace_recorder",
    "get_trace_recorder",
    "trace_context",
    "current_trace_context",
    # For callers that reach a provider themselves — embeddings, say — and so
    # trace a call this package never makes.
    "traced_call",
    "trace_outcome",
    "generate",
    "generate_stream",
    "generate_structured",
    "tool_loop",
    "run_tool_loop",
    "ToolLoopResult",
    "ToolExecutor",
    # Turn-scoped working-memory the loop renders as a board and the writer reads.
    "Scratchpad",
    "Handle",
    "Preview",
    # What `tool_loop` yields as it goes; `ToolLoopFinished` is always last.
    "ToolLoopEvent",
    "ToolCallStarted",
    "ToolCallFinished",
    "ToolLoopFinished",
    # For callers that build their own OpenAI-compatible client — embeddings,
    # say — and must not outlive the loop its connection pool belongs to.
    "get_async_openai",
    "aclose_async_openai",
    "LLMError",
    "ProviderError",
    "MissingCredentialError",
    "LLMDisabledError",
    "ToolExecutionError",
    "MaxIterationsError",
]
