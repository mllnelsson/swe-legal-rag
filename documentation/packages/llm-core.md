---
type: Package
title: llm-core Package
description: The standalone, project-agnostic LLM abstraction — provider Protocol, config/factory, Gemini and OpenAI-compatible providers, the service layer, and the trace hook.
resource: packages/llm-core
tags: [package, llm, provider, abstraction]
timestamp: 2026-08-02T00:00:00Z
---

# llm-core Package (`packages/llm-core/`)

Standalone, project-agnostic LLM abstraction. **Zero dependency on `shared`** — fully
reusable across projects. It knows nothing about this domain; project-specific logic
lives in the [ai package](/packages/ai.md).

## Modules

- **`_types.py`** — frozen dataclasses: `Message`, `ToolCall`, `ToolDefinition`,
  `LLMResponse`, `StreamChunk`, `Usage`, `Role` (StrEnum). `LLMResponse` and
  `StreamChunk` each carry `usage`, `model` and `provider`; `Usage` fields are
  `None` when the provider reported nothing, which is not the same as zero.
- **`_exceptions.py`** — `LLMError` base, `ProviderError`, `MissingCredentialError` (a
  provider constructed without the API key or base URL it needs), `ToolExecutionError`,
  `MaxIterationsError`.
- **`_protocol.py`** — `LLMProvider` Protocol (`@runtime_checkable`) with `generate()`
  and `generate_stream()`. Providers do one round-trip; the tool-call loop is in the
  service layer.
- **`_config.py`** — `ProviderKind` (`StrEnum`): `OPENAI_COMPATIBLE` or `GEMINI`, the
  client implementation a provider entry maps onto. A *kind* is a wire protocol, not a
  vendor — every host speaking the OpenAI chat-completions API is one
  `OPENAI_COMPATIBLE` entry apart, distinguished by `base_url` alone, so adding such a
  host needs no code.

  `LLMConfig(BaseSettings)` reads `LLM_PROVIDER` (default `openai_compatible`, typed as
  `ProviderKind`), `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_API_KEY`,
  `LLM_BASE_URL`, `LLM_STREAM_USAGE`. `create_provider()` is a factory with lazy-import
  dispatch on `config.provider`: `ProviderKind.GEMINI` → `GeminiProvider`,
  `ProviderKind.OPENAI_COMPATIBLE` → `OpenAiCompatibleProvider`. There is no fallback
  `case` — `provider` is a `ProviderKind`, so pydantic rejects an unrecognized value when
  the config is built, at the point the bad setting was supplied rather than at dispatch.

  `api_key` is the **only** credential field — a host-agnostic value populated by the
  caller, as [`ai.llm_config`](/reference/llm-config.md) does, from the variable each
  provider entry's `api_key_env` names. There is no per-host named field (no
  `berget_api_key` / `gemini_api_key`) and no built-in default `base_url`; a provider
  constructed without either raises `MissingCredentialError` rather than silently
  falling back.

  Note that in this project nothing resolves a role's model through `LLM_MODEL` —
  see [per-task model selection](/packages/ai.md).
- **`_tracing.py`** — the observability hook: `LLMOperation`, `LLMCallRecord`, the
  `TraceRecorder` Protocol, `set_trace_recorder()`, the ContextVar-backed
  `trace_context()`, and the `traced_call()` context manager that opens and closes
  exactly one record. See [LLM Observability](/observability.md).
- **`providers/_gemini.py`** — Gemini implementation using the `google-genai` SDK (the
  unified SDK, not deprecated `google-generativeai`). Fully supported, selectable via
  `LLM_PROVIDER=gemini`.
- **`providers/_openai_compatible.py`** — `OpenAiCompatibleProvider`, a generic client
  for any OpenAI-chat-completions-compatible API using the `openai` SDK (`AsyncOpenAI`).
  [Berget.ai](https://docs.berget.ai) is the vendor this project points it at by default,
  but the class takes no Berget-specific behavior: both `api_key` and `base_url` are
  required constructor inputs (raising `MissingCredentialError` if either is missing)
  rather than defaulted, so a second OpenAI-compatible host (Groq, Together, a local
  vLLM) is a new entry under `providers:` in
  [`llm_config.yaml`](/reference/llm-config.md) naming its `base_url` and `api_key_env`
  — no new provider class, and no code change at all. Maps
  `Message`/`ToolDefinition`/`response_schema` to OpenAI's chat-completions shape (tool
  calls, `response_format` json_schema for structured output) and wraps SDK exceptions
  in `ProviderError`.
- **`_service.py`** — the higher-level API: `generate()`, `generate_structured()`,
  `generate_stream()`, `tool_loop()` with optional callbacks. All four emit one trace
  record per billed provider round-trip. `generate_structured[T: BaseModel]` is generic
  in its `response_model`, so callers get the model they asked for and need no cast,
  `assert isinstance`, or `type: ignore` to narrow it.

Both providers map the token usage the SDK reports onto `Usage`, and record the model
the API says it **served** rather than the one configured — hosts resolve aliases to
dated builds, and cost must attach to what actually ran. Gemini's thinking tokens are
folded into output, since they bill at the output rate but are excluded from
`candidates_token_count`.

## Tracing: the hook, never the writer

llm-core defines what a traced call looks like and where a recorder plugs in. It never
writes one. That is what lets the package stay free of any dependency on the rest of the
project — the concrete recorder lives in [ai](/packages/ai.md).

A trace is opened and closed by **one context manager**, never by hand:

```python
with traced_call(LLMOperation.generate, messages) as trace:
    response = await provider.generate(messages)
    trace_response(trace, response)
```

`traced_call()` owns the record's lifecycle — leaving the block cleanly marks the call
successful, leaving by exception records the failure, and either way the record is handed
over exactly once. It catches `BaseException`, not `Exception`: a consumer abandoning a
stream closes the generator, which arrives as `GeneratorExit`, and that call is worth
recording precisely because it was paid for and never delivered. The block only supplies
the payload the provider returned, through one of three folds:

| Fold | For |
|---|---|
| `trace_response(trace, response)` | a non-streaming `LLMResponse` |
| `trace_chunk(trace, chunk)` | one `StreamChunk`, called per chunk |
| `trace_outcome(trace, usage=…, model=…, provider=…)` | a call llm-core did not make |

`trace_outcome()` is the extension point for callers that reach a provider directly —
[embeddings](/packages/ai.md) — and so have usage and attribution but no `LLMResponse`.
`traced_call()` also takes `model` and `provider` up front for callers that know them
before the call, so a request that never returns is still attributed rather than blank.
None never overwrites a value already recorded, so late and cumulative usage reports
settle on the last one.

`TraceRecorder.record` is **synchronous and must not raise**. A stream records from a
`finally` that may be unwinding under `GeneratorExit`, where awaiting anything that
suspends raises `RuntimeError`; and workers call `asyncio.run()` per message, which
cancels pending tasks at teardown and would silently drop a fire-and-forget write. A
recorder needing I/O hands off to its own thread.

With no recorder installed `traced_call()` yields `None`, every fold no-ops, and the
package behaves exactly as it did before tracing existed — at the cost of one global read
per call.

## llm-core / ai boundary

These two packages have distinct responsibilities and must not be confused:

- **`llm-core`** — generic LLM abstraction. Zero dependency on `shared`.
- **`ai`** — project-specific LLM logic; depends on both `shared` and `llm-core`.

**Rule:** `ai` calls `llm-core` — never the SDK (google-genai / openai) directly. New use
cases go in `ai`, not `llm-core`.
