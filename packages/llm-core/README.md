# llm-core

The provider abstraction and the tool loop. This is the layer everything else
stands on: it knows how to talk to an LLM host and how to run an agentic
tool-calling loop, and it knows *nothing* about your app, your prompts or your
corpus. `agent-kit` sits directly on top of it; a host rarely calls `llm-core`
except for its types.

It depends only on `pydantic`, `pydantic-settings`, `openai` and `google-genai`.
It imports nothing from this repo.

## What it gives you

| Concern | You get |
| --- | --- |
| Wire types | `Message`, `Role`, `ToolCall`, `ToolDefinition`, `LLMResponse`, `StreamChunk`, `Usage` |
| Provider | `LLMProvider` (a Protocol), `create_provider(LLMConfig)`, `ProviderKind` |
| One call | `generate`, `generate_stream`, `generate_structured` |
| Agentic loop | `tool_loop` (streams events), `run_tool_loop` (awaits a result), `ToolExecutor` |
| Tracing hook | `set_trace_recorder`, `trace_context`, `traced_call` — the seam a host writes traces through |
| Errors | `LLMError`, `ProviderError`, `MissingCredentialError`, `LLMDisabledError`, `ToolExecutionError`, `MaxIterationsError` |

## The three provider kinds

`ProviderKind` is the wire protocol, not the vendor:

- `openai_compatible` — anything speaking the OpenAI Chat Completions API (OpenAI,
  most self-hosted gateways, Berget, together, groq, …). Needs a `base_url` and an
  API key.
- `gemini` — Google's native API. Needs an API key.
- `none` — the null provider. Constructs without credentials and raises
  `LLMDisabledError` if anything actually calls it. This is how a process that
  makes *no* LLM calls (an ingestion step, a test) runs with no keys configured.

You almost never build a provider by hand — `agent_kit.create_llm_provider("role")`
reads your config file and does it. But the shape, if you need it:

```python
from llm_core import LLMConfig, ProviderKind, create_provider

provider = create_provider(
    LLMConfig(
        provider=ProviderKind.openai_compatible,
        base_url="https://api.openai.com/v1",
        api_key="sk-…",
        model="gpt-4o-mini",
        temperature=0.0,
    )
)
```

## The tool loop

`tool_loop` is the agentic core: it sends the messages, and while the model asks
for tools it runs your executors and feeds their results back, until the model
calls a terminal tool or the iteration budget runs out.

An **executor** is `async def (**arguments) -> Any` — the model's tool-call
arguments are passed by keyword, so the parameter names must match the tool's JSON
schema. What it returns is the tool result the model sees next turn.

```python
from llm_core import ToolDefinition, tool_loop, Message, Role

SEARCH = ToolDefinition(
    name="search",
    description="Full-text search the knowledge base.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)

async def search(query: str) -> dict:
    return {"hits": await my_index.search(query)}

async for event in tool_loop(
    [Message(role=Role.user, content="find the refund policy")],
    tools=[SEARCH, ANSWER],
    executors={"search": search, "answer": answer},
    provider=provider,
    max_iterations=6,
    terminal_tools={"answer"},
):
    ...  # ToolCallStarted, ToolCallFinished, ToolLoopFinished
```

**The decline convention.** A tool that wants to refuse a call — an ungrounded
filter, a budget reached — returns a dict with an `"error"` key (and `"refused":
True` when the decline is on policy rather than a fault) instead of raising. The
loop feeds that back to the model, which repairs itself. Raising from an executor
is for genuine defects and surfaces as `ToolExecutionError`.

`run_tool_loop` is the same loop without the event stream: it returns a
`ToolLoopResult` with the final message. `agent-kit`'s plan phase uses it for its
single, one-shot planning call.

## Tracing

`llm-core` never writes a trace itself — it emits an `LLMCallRecord` for every
billed call and hands it to whatever `TraceRecorder` a host installed via
`set_trace_recorder`. `agent-kit` ships the concrete file recorder
(`install_file_tracing`); this package only defines the hook and the
`trace_context(source=…, prompt=…)` scope that tags each record. If you reach a
provider yourself (embeddings, say), wrap the call in `traced_call` so it lands in
the same trace tree.

## Copying it into another project

`llm-core` and `agent-kit` travel together — bring both. See
`packages/agent-kit/README.md` for the full checklist and a worked example.
