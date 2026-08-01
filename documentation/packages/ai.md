---
type: Package
title: ai Package
description: Project-specific LLM logic — prompt templates, domain DTOs, service functions, per-task model selection, the embedding abstraction, and the LLM trace recorder.
resource: packages/ai
tags: [package, ai, prompts, embedding, llm]
timestamp: 2026-08-01T00:00:00Z
---

# ai Package (`packages/ai/`)

Project-specific LLM logic consuming [llm-core](/packages/llm-core.md). Knows about
Swedish legal documents; provides domain DTOs, prompt templates, service functions, and
the embedding abstraction. Depends on both `shared` and `llm-core`.

## Module layout

| Module | Role |
|---|---|
| `dtos.py` | All domain DTOs — frozen Pydantic v2 models for every LLM use case |
| `_observability.py` | `FileTraceRecorder`, `LLMTraceConfig`, `install_file_tracing()` — writes LLM traces to file storage |
| `services.py` | Five async service functions (below) |
| `llm_config.py` | Reads `llm_config.yaml` — document models, discovery, and role/embedding resolution |
| `embedding.py` | `EmbeddingProvider` Protocol, `create_embedding_provider` factory, `verify_embedding_dimension` |
| `providers/berget_embeddings.py` | `BergetEmbeddingProvider` — Berget's hosted embedding API (default) |
| `providers/local_embeddings.py` | `LocalEmbeddingProvider` — `sentence-transformers` (offline dev/test fallback) |
| `providers/roles.py` | `create_llm_provider(role)` + the three named delegates (per-task model assignment, below) |
| `prompts/_renderer.py` | `PromptTemplate` frozen dataclass + `render()` free function |
| `prompts/_templates.py` | The five template constants |
| `__init__.py` | Public API — service functions, embedding types, and DTOs |

## Prompt templates (`ai/prompts/`)

`PromptTemplate` is a frozen dataclass holding just data (`name`, `system_prompt`,
`user_template`). The `name` is what identifies the prompt in a trace record — `render()`
returns a plain message list, so nothing downstream could otherwise tell which template
produced it. Rendering is a **free function** `render(template, context) ->
list[Message]` — it substitutes variables via `str.format_map(context)` and returns
`[Message(SYSTEM, system_prompt), Message(USER, rendered_user)]`. Five template constants
cover every use case:

| Constant | Output format | User template variables |
|---|---|---|
| `QUERY_DECOMPOSITION` | JSON (`DecomposeResult` schema) | `{question}`, `{conversation_history}` |
| `ANSWER_SYNTHESIS` | Plain Swedish text with case citations | `{question}`, `{chunks}`, `{conversation_history}` |
| `METADATA_EXTRACTION` | JSON (`MetadataResult` schema) | `{raw_text}` |
| `ENTITY_EXTRACTION` | JSON (`EntityResult` schema) | `{raw_text}`, `{case_number}` |
| `DOCUMENT_SUMMARIZATION` | Plain Swedish text | `{raw_text}` |

All JSON-outputting templates embed the exact field schema in their system prompt, and
all prompts instruct the model to work in Swedish.

## Service functions (`ai/services.py`)

| Function | LLM call |
|---|---|
| `decompose_query(question, conversation_history=None, *, provider=None) -> DecomposeResult` | `generate_structured` |
| `extract_metadata(raw_text, *, provider=None) -> MetadataResult` | `generate_structured` |
| `extract_entities(raw_text, case_number=None, *, provider=None) -> EntityResult` | `generate_structured` |
| `summarize_document(raw_text, *, provider=None) -> SummarizeResult` | `generate` |
| `synthesize_answer(request, *, provider=None) -> AsyncIterator[str]` | `generate_stream` |

`synthesize_answer` is an async generator (SSE critical path): it formats chunks with
`[Mål {case_number}]` prefixes, renders `ANSWER_SYNTHESIS`, and yields tokens without
buffering.

## Domain DTOs (`ai/dtos.py`)

All DTOs are `frozen=True` Pydantic v2 models; consumers depend on them, so fields are not
removed or renamed.

| Domain | Request | Result |
|---|---|---|
| Query decomposition | `DecomposeRequest` | `DecomposeResult` (with `DateFilter`) |
| Answer synthesis | `SynthesizeRequest` (with `ChunkContext`) | streaming `str` tokens; `SourceCitation` for UI |
| Metadata extraction | `MetadataRequest` | `MetadataResult` |
| Entity & reference extraction | `EntityRequest` | `EntityResult` (with `ExtractedEntity`, `ExtractedReference`) |
| Summarization | `SummarizeRequest` | `SummarizeResult` |
| Embedding | `EmbedRequest` | `EmbedResult` |

`ChunkContext.score: float` is required (no default).

## Configuration (`ai/llm_config.py`)

Reads [`llm_config.yaml`](/reference/llm-config.md) — which model and provider each task
uses — and resolves it into the settings objects the rest of the package consumes. The
loader lives here rather than in [llm-core](/packages/llm-core.md) because llm-core is
project-agnostic and knows nothing about a file at this project's root.

| Function | Returns |
|---|---|
| `get_llm_config()` | The validated `LLMConfigDocument`, read once (`@lru_cache`) |
| `resolve_role_config(role)` | An `llm_core.LLMConfig` for a named role |
| `resolve_embedding_config()` | An `EmbeddingConfig` |
| `get_embedding_prefixes()` | `(query_prefix, passage_prefix)` |
| `find_config_path()` / `load_config_document(path)` | Discovery and parsing, for tests and tooling |
| `role_model_env_var(role)` | That role's override variable, `LLM_MODEL_<ROLE>` |

Discovery is `LLM_CONFIG_PATH`, else a walk up from the working directory (pytest runs
from package subdirectories in this workspace). **A missing or malformed file is fatal**
— `LLMConfigNotFoundError` / `LLMConfigInvalidError`, and every document model sets
`extra="forbid"` so a mistyped key fails at load. There is deliberately no fallback to
built-in defaults: a silent fallback is how the documented configuration and the running
one drift apart, which has happened here before (see [the log](/log.md)).

Environment variables override the file, which inverts pydantic-settings' native
ordering — the [precedence rules](/reference/llm-config.md#precedence) explain the
mechanism.

## Per-task model selection (`ai/providers/roles.py`)

`llm_core.LLMConfig` carries one `model` field. This project needs a different model —
and sometimes a different provider — per task, so the assignment lives in
`llm_config.yaml` under `roles:`. See
[the decision record](/decisions/llm-model-selection.md) for why.

| Role | Used by | Default (Berget model) |
|---|---|---|
| `structured` | `decompose_query`, `extract_metadata`, `extract_entities`, `retriever._rerank` | `mistralai/Mistral-Small-3.2-24B-Instruct-2506` |
| `summarize` | `summarize_document` | `mistralai/Mistral-Medium-3.5-128B` |
| `chat` | `synthesize_answer` | `zai-org/GLM-5.2` |

`create_llm_provider(role)` builds the provider for any role declared in the file;
`create_structured_llm_provider()`, `create_summarize_llm_provider()` and
`create_chat_llm_provider()` are one-line delegates for the three that have call sites.
**The role set is open** — declaring `rerank:` in the YAML is enough to call
`create_llm_provider("rerank")`, with no Python change and no new environment variable.
An undeclared role raises `UnknownLLMRoleError`.

Each composition root constructs the role-appropriate provider(s) once at startup and
threads them into the call sites via the `provider=` keyword — no hidden global default
in production.

**Gemini caveat.** The defaults above are Berget model IDs and will not resolve against
Gemini's API, so pointing a role at `provider: gemini` means changing its `model:` in the
same edit (e.g. `gemini-2.5-flash-lite`, since `gemini-2.0-flash` was shut down — see
[LLM pricing](/reference/llm-pricing.md)).

## Embedding abstraction (`ai/embedding.py`)

`EmbeddingProvider` is a `@runtime_checkable` Protocol with one method:
`async embed(texts) -> list[list[float]]`. `EmbeddingConfig` is defined in
`ai/llm_config.py` (and re-exported here) and carries `provider`, `model`, `dimension`,
`api_key` and `base_url`, resolved from `llm_config.yaml`'s `embedding:` block — the
base URL and key variable come from the same `providers:` entry the LLM roles use, so
one Berget account/key covers both. `create_embedding_provider()` dispatches on the
resolved backend (`local`, or the host's kind) and lazy-imports the concrete class, so
the heavy ML library loads only for the local provider and `openai` only for the hosted
one.

`verify_embedding_dimension(provider, config=None)` is the startup guard. It checks
**three** declarations of the width against each other — `embedding.dimension` in the
YAML, `shared.config.EMBEDDING_DIMENSION`, and the width the model actually produces for
a probe string — and raises `EmbeddingDimensionMismatchError` naming the disagreement.
See [embedding dimension](/decisions/embedding-dimension.md).

`get_embedding_prefixes()` returns the `(query, passage)` pair for the configured model.
Both sides come from one place so they cannot drift apart; the query half is used by the
[retrieval agent](/retrieval/agent.md) and the passage half by
[worker-embed](/pipeline/embed.md).

- **`BergetEmbeddingProvider`** (default, `EMBEDDING_PROVIDER=berget`) — calls Berget's
  hosted `intfloat/multilingual-e5-large` via `openai.AsyncOpenAI.embeddings.create()`.
  **Traced**: embedding runs once per chunk over the whole corpus, so it is plausibly
  the largest single line of token spend.
- **`LocalEmbeddingProvider`** (`EMBEDDING_PROVIDER=local`) — `sentence-transformers`
  in-process; the offline dev/test fallback. **Not traced** — no API call, no token
  accounting, and a contribution of exactly zero to what a question cost.

Tracing sits inside `BergetEmbeddingProvider` rather than in a wrapper: a wrapper
implementing `EmbeddingProvider` could time the call but not see token usage, since
`embed() -> list[list[float]]` has nowhere to put it. The embedded texts are not
recorded — they are chunk text already durable in Postgres — only their count and
character total.

Because the call bypasses llm-core's service layer, the provider opens its own trace with
`traced_call()` and reports usage through `trace_outcome()` — the same context manager
llm-core uses internally, so the lifecycle is not hand-rolled here. Model and provider are
seeded on entry from config, which means a timeout is still attributed to the right model;
whatever the API reports back overrides the seed. See
[llm-core](/packages/llm-core.md).

See the [embedding hosting](/decisions/embedding-hosting.md) decision. The width
constraint and its startup verification (`verify_embedding_dimension`) are covered in
[embedding dimension](/decisions/embedding-dimension.md).

## Trace recording (`ai/_observability.py`)

`ai` supplies the concrete recorder behind llm-core's hook. It belongs here because it
needs both llm-core's record type and `shared`'s storage layer, and `shared` must not
depend on llm-core.

`install_file_tracing(storage=None)` is called **once at startup** by every process that
makes LLM calls — the API lifespan and each of the four LLM workers. It never raises: a
backend it cannot build leaves no recorder at all, and llm-core treats that as tracing
off. `trace_context` is re-exported here so callers need no direct llm-core dependency.

The recorder owns the **storage layout**, which is why `shared`'s `StorageBackend` stayed
a five-method blob store. Records are queued, batched, serialized as JSONL, and written
as whole objects with `store()` — so an object store, which cannot append, never has to.
Batching is what makes that path viable: embedding runs once per chunk over the whole
corpus, and an object per call would be hundreds of thousands of tiny billed writes.

Cost is **not** written into the record, and there is no rate table in this package.
A record carries the served `model` and the provider's `usage`, which is the complete
raw material — applying a price to it is an analysis question, answered against
[LLM pricing](/reference/llm-pricing.md) when the traces are analyzed. Computing it here
would only freeze a rate that may be wrong or, as today, missing: no Berget rate is
published in this repo, so every record would carry a null that could never be filled
in.

Full record schema, correlation keys and the wiring invariant:
[LLM Observability](/observability.md). Rate rules: [LLM pricing](/reference/llm-pricing.md).

## Adding a new LLM use case

1. Add `YourRequest`/`YourResult` (`frozen=True`) to `ai/dtos.py`.
2. Add a `PromptTemplate` constant to `ai/prompts/_templates.py`, including its `name`.
3. Add a service function to `ai/services.py` (render the template, call
   `generate_structured`/`generate`/`generate_stream` inside a `trace_context` naming
   the `source` and `prompt`).
4. Export from `__init__.py`.
5. Add a unit test mocking `ai.services.generate_structured`.
