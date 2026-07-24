---
type: Package
title: llm-core Package
description: The standalone, project-agnostic LLM abstraction — provider Protocol, config/factory, Gemini and OpenAI-compatible providers, and the service layer.
resource: packages/llm-core
tags: [package, llm, provider, abstraction]
timestamp: 2026-07-24T00:00:00Z
---

# llm-core Package (`packages/llm-core/`)

Standalone, project-agnostic LLM abstraction. **Zero dependency on `shared`** — fully
reusable across projects. It knows nothing about this domain; project-specific logic
lives in the [ai package](/packages/ai.md).

## Modules

- **`_types.py`** — frozen dataclasses: `Message`, `ToolCall`, `ToolDefinition`,
  `LLMResponse`, `StreamChunk`, `Role` (StrEnum).
- **`_exceptions.py`** — `LLMError` base, `ProviderError`, `ToolExecutionError`,
  `MaxIterationsError`.
- **`_protocol.py`** — `LLMProvider` Protocol (`@runtime_checkable`) with `generate()`
  and `generate_stream()`. Providers do one round-trip; the tool-call loop is in the
  service layer.
- **`_config.py`** — `LLMConfig(BaseSettings)` reading `LLM_PROVIDER` (default
  `"berget"`), `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `GEMINI_API_KEY`,
  `BERGET_API_KEY`, `LLM_BASE_URL`. `create_provider()` is a factory with lazy-import
  dispatch: `"gemini"` → `GeminiProvider`, `"berget"` → `OpenAiCompatibleProvider`.
- **`providers/_gemini.py`** — Gemini implementation using the `google-genai` SDK (the
  unified SDK, not deprecated `google-generativeai`). Fully supported, selectable via
  `LLM_PROVIDER=gemini`.
- **`providers/_openai_compatible.py`** — `OpenAiCompatibleProvider`, a generic client
  for any OpenAI-chat-completions-compatible API using the `openai` SDK (`AsyncOpenAI`).
  [Berget.ai](https://docs.berget.ai) is the first and default host (`LLM_PROVIDER=berget`,
  base URL `https://api.berget.ai/v1`). The class is not Berget-specific: `LLM_BASE_URL`
  overrides the base URL, so a second OpenAI-compatible host needs a config value, not a
  new provider class. Maps `Message`/`ToolDefinition`/`response_schema` to OpenAI's
  chat-completions shape (tool calls, `response_format` json_schema for structured
  output) and wraps SDK exceptions in `ProviderError`.
- **`_service.py`** — the higher-level API: `generate()`, `generate_structured()`,
  `generate_stream()`, `tool_loop()` with optional callbacks.

## llm-core / ai boundary

These two packages have distinct responsibilities and must not be confused:

- **`llm-core`** — generic LLM abstraction. Zero dependency on `shared`.
- **`ai`** — project-specific LLM logic; depends on both `shared` and `llm-core`.

**Rule:** `ai` calls `llm-core` — never the SDK (google-genai / openai) directly. New use
cases go in `ai`, not `llm-core`.
