from llm_core._config import LLMConfig, create_provider
from llm_core._exceptions import (
    LLMError,
    MaxIterationsError,
    ProviderError,
    ToolExecutionError,
)
from llm_core._protocol import LLMProvider
from llm_core._service import (
    ToolCallCallback,
    ToolExecutor,
    ToolLoopResult,
    ToolResultCallback,
    generate,
    generate_stream,
    generate_structured,
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

__all__ = [
    "LLMConfig",
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
    "ToolLoopResult",
    "ToolExecutor",
    "ToolCallCallback",
    "ToolResultCallback",
    "LLMError",
    "ProviderError",
    "ToolExecutionError",
    "MaxIterationsError",
]
