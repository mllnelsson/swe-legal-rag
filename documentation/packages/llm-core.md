---
type: Package
title: llm-core Package
description: The standalone, project-agnostic LLM abstraction — provider Protocol, config/factory, Gemini and OpenAI-compatible providers, the service layer, and the trace hook.
resource: packages/llm-core
tags: [package, llm, provider, abstraction]
timestamp: 2026-08-22T00:00:00Z
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
  provider constructed without the API key or base URL it needs), `LLMDisabledError`
  (something called a provider deliberately configured as absent — the mirror image of
  `MissingCredentialError`, which means the configuration was meant to be there and was
  not), `ToolExecutionError`, `MaxIterationsError`.
- **`_protocol.py`** — `LLMProvider` Protocol (`@runtime_checkable`) with `generate()`
  and `generate_stream()`. Providers do one round-trip; the tool-call loop is in the
  service layer.
- **`_config.py`** — `ProviderKind` (`StrEnum`): `OPENAI_COMPATIBLE`, `GEMINI` or
  `NONE`, the client implementation a provider entry maps onto. A *kind* is a wire
  protocol, not a vendor — every host speaking the OpenAI chat-completions API is one
  `OPENAI_COMPATIBLE` entry apart, distinguished by `base_url` alone, so adding such a
  host needs no code. `NONE` is a kind too, not the absence of one: "there is
  deliberately no model here" is a configuration, and making it a member keeps dispatch
  exhaustive instead of putting a second switch beside it.

  `LLMConfig(BaseSettings)` reads `LLM_PROVIDER` (default `openai_compatible`, typed as
  `ProviderKind`), `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_API_KEY`,
  `LLM_BASE_URL`, `LLM_STREAM_USAGE`. `create_provider()` is a factory with lazy-import
  dispatch on `config.provider`: `ProviderKind.GEMINI` → `GeminiProvider`,
  `ProviderKind.OPENAI_COMPATIBLE` → `OpenAiCompatibleProvider`, `ProviderKind.NONE` →
  `NullProvider`. There is no fallback `case` — `provider` is a `ProviderKind`, so
  pydantic rejects an unrecognized value when the config is built, at the point the bad
  setting was supplied rather than at dispatch.

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
  in `ProviderError`. `__init__` only validates credentials — it does **not** build the
  SDK client; every call fetches one from `llm_core._clients.get_async_openai()`
  instead, per [loop-bound clients](#loop-bound-clients-_clientspy) below.
- **`providers/_null.py`** — `NullProvider`, a provider configured to not exist.
  Constructing it always succeeds: no key, no base URL, no client library, so a process
  whose LLM steps are switched off starts normally instead of dying on a credential it
  will never use. Every call raises `LLMDisabledError` naming the operation and the
  model that was requested. `generate_stream` refuses on `await`, not part-way through
  an `async for` — it is a coroutine returning an iterator, the same shape as the real
  providers. Selected with `kind: none` in
  [`llm_config.yaml`](/reference/llm-config.md) or `LLM_PROVIDER=none`; what each
  pipeline step then does is tabulated there.
- **`_service.py`** — the higher-level API: `generate()`, `generate_structured()`,
  `generate_stream()`, `tool_loop()`, `run_tool_loop()`. All emit one trace record per
  billed provider round-trip. `generate_stream` takes no `tools` — a limit of this
  project's own OpenAI-compatible wrapper, not the underlying API, which streams tool
  calls fine — so an agent that both plans with tools and streams a written answer still
  does it as two calls: gather with `tool_loop`, then write with one `generate_stream`
  call over what was gathered. [The conversational agent](/retrieval/chat-agent.md)
  explains why that split is worth keeping even where the wrapper's limit is not.

  `tool_loop` is an **async generator**, not a coroutine returning a value: it yields
  `ToolCallStarted`, `ToolCallFinished` and, always last, `ToolLoopFinished` (carrying
  the `ToolLoopResult`) as the run goes, so a caller that needs to *yield* per step — an
  SSE generator, say — drives it with a plain `async for` instead of routing a callback
  through a queue. A generator cannot `return` a value, which is why the result travels
  as that final event rather than as one; `run_tool_loop(...)` drains the generator for a
  caller that wants only the result, unchanged in shape from before (the [SQL
  agent](/api/sql-agent.md) uses this).

  `tool_loop` takes an optional `terminal_tools: set[str]`. Naming a tool there means
  the loop executes it and ends the run rather than looping again. Without it a run ends
  only when the model happens to stop calling tools, which makes termination incidental
  and the final assistant message throwaway prose; with it the ending is deliberate and
  the *arguments* of the terminal call are the result. `ToolLoopResult.message` is then
  the assistant message carrying that call. Any later call in the same turn is left
  unexecuted, so the returned `history` can end on an assistant message with an
  unanswered tool call and is not safe to resume a provider round-trip with. A run can
  also end with **no terminal call at all** — the model simply stops calling tools and
  answers in prose — and `ToolLoopFinished.result.message.tool_calls` is empty in that
  case; a caller has to check for it rather than assume every ending named a terminal
  tool. `generate_structured[T: BaseModel]` is generic in its `response_model`, so
  callers get the model they asked for and need no cast, `assert isinstance`, or `type:
  ignore` to narrow it.

Both providers map the token usage the SDK reports onto `Usage`, and record the model
the API says it **served** rather than the one configured — hosts resolve aliases to
dated builds, and cost must attach to what actually ran. Gemini's thinking tokens are
folded into output, since they bill at the output rate but are excluded from
`candidates_token_count`.

## Loop-bound clients (`_clients.py`)

An `AsyncOpenAI` client owns an `httpx` connection pool, and a pooled connection
belongs to the event loop that opened it — the same rule
[`shared.db`](/packages/shared.md) already applies to the asyncpg engine. Every worker
that makes LLM calls runs `asyncio.run()` once per queue message
([worker patterns](/pipeline/worker-patterns.md)), so a client built once in a
provider's `__init__` handed the *second* message a connection whose loop had already
closed: that first attempt failed instantly with no HTTP response, and the SDK's
generic retry silently absorbed it onto a fresh connection, which was then pooled for
the next dead loop in turn. The 2020-2026 ingest logged **219 retries against 221
calls** this way — every one the SDK's first retry, every underlying response `200 OK`.

`get_async_openai(*, api_key, base_url) -> AsyncOpenAI` keys a client cache on
`(running loop, api_key, base_url)`, so a caller inside a loop always gets the client
that belongs to it — built once and reused for the rest of that loop's calls, and
never handed across a loop boundary. `OpenAiCompatibleProvider` and
[`OpenAiCompatibleEmbeddingProvider`](/packages/ai.md) both call it per request instead
of holding a client as an attribute. `aclose_async_openai()` is the counterpart to
`shared.db.dispose_async_engine()`: whoever owns a loop for one unit of work must
await it before that loop closes, or the pool never actually releases its sockets.
Skipping it does not leak the cache entry — a closed loop's entry is dropped on the
next lookup — but it is noisy, since `AsyncOpenAI.__del__` schedules a close on
whatever loop happens to be running when garbage collection reaches it.

`shared.worker.subscribe_step` takes teardown as an injected `StepTeardown` parameter
for exactly this reason — `shared` must not depend on `llm-core`, so it cannot call
`aclose_async_openai()` itself. Every LLM-calling worker (chunk, embed, extract,
metadata) passes `ai.close_llm_clients`, which awaits it; worker-download and
worker-parse make no LLM calls and pass no teardown. See [worker
patterns](/pipeline/worker-patterns.md). A process with one long-lived loop — the API
server's lifespan — builds one client per set of credentials and keeps its keep-alive
pool for the process lifetime, exactly as before this existed.

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
recorder whose I/O is slow enough to matter — a network filesystem, an object store —
should buffer internally; a local file write is not, which is why the shipped recorder
(`ai.FileTraceRecorder`, see [observability](/observability.md)) writes inline instead
of handing off to a thread.

With no recorder installed `traced_call()` yields `None`, every fold no-ops, and the
package behaves exactly as it did before tracing existed — at the cost of one global read
per call.

## llm-core / ai boundary

These two packages have distinct responsibilities and must not be confused:

- **`llm-core`** — generic LLM abstraction. Zero dependency on `shared`.
- **`ai`** — project-specific LLM logic; depends on both `shared` and `llm-core`.

**Rule:** `ai` calls `llm-core` — never the SDK (google-genai / openai) directly. New use
cases go in `ai`, not `llm-core`.
