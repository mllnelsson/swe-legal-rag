---
type: Package
title: ai Package
description: Project-specific LLM logic — prompt templates, domain DTOs, service functions, per-task model selection, and the embedding abstraction.
resource: packages/ai
tags: [package, ai, prompts, embedding, llm]
timestamp: 2026-07-24T00:00:00Z
---

# ai Package (`packages/ai/`)

Project-specific LLM logic consuming [llm-core](/packages/llm-core.md). Knows about
Swedish legal documents; provides domain DTOs, prompt templates, service functions, and
the embedding abstraction. Depends on both `shared` and `llm-core`.

## Module layout

| Module | Role |
|---|---|
| `dtos.py` | All domain DTOs — frozen Pydantic v2 models for every LLM use case |
| `services.py` | Five async service functions (below) |
| `embedding.py` | `EmbeddingProvider` Protocol, `EmbeddingConfig`, `create_embedding_provider` factory |
| `providers/berget_embeddings.py` | `BergetEmbeddingProvider` — Berget's hosted embedding API (default) |
| `providers/local_embeddings.py` | `LocalEmbeddingProvider` — `sentence-transformers` (offline dev/test fallback) |
| `providers/roles.py` | `LLMRoleConfig` + per-role provider factories (per-task model assignment, below) |
| `prompts/_renderer.py` | `PromptTemplate` frozen dataclass + `render()` free function |
| `prompts/_templates.py` | The five template constants |
| `__init__.py` | Public API — service functions, embedding types, and DTOs |

## Prompt templates (`ai/prompts/`)

`PromptTemplate` is a frozen dataclass holding just data (`system_prompt`,
`user_template`). Rendering is a **free function** `render(template, context) ->
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

## Per-task model selection (`ai/providers/roles.py`)

`llm_core.LLMConfig` carries one `model` field. This project needs three models for three
cost/quality profiles — extraction/decomposition/rerank run once per document at
ingestion scale, while chat synthesis runs a handful of times per day:

| Role | Used by | Env var | Default (Berget model) |
|---|---|---|---|
| `structured` | `decompose_query`, `extract_metadata`, `extract_entities`, `retriever._rerank` | `LLM_MODEL_STRUCTURED` | `mistralai/Mistral-Small-3.2-24B-Instruct-2506` |
| `summarize` | `summarize_document` | `LLM_MODEL_SUMMARIZE` | `mistralai/Mistral-Medium-3.5-128B` |
| `chat` | `synthesize_answer` | `LLM_MODEL_CHAT` | `zai-org/GLM-5.2` |

`create_structured_llm_provider()`, `create_summarize_llm_provider()`, and
`create_chat_llm_provider()` each build an `llm_core.LLMConfig` overriding only `model`;
`provider`/`BERGET_API_KEY`/`LLM_BASE_URL`/temperature resolve from the environment. Each
composition root constructs the role-appropriate provider(s) once at startup and threads
them into the call sites via the `provider=` keyword — no hidden global default in
production.

**Gemini fallback caveat.** The three `LLM_MODEL_*` defaults are Berget model IDs.
Switching `LLM_PROVIDER=gemini` also requires overriding all three to valid Gemini model
names (e.g. `gemini-2.5-flash-lite`, since `gemini-2.0-flash` was shut down — see
[LLM pricing](/reference/llm-pricing.md)).

## Embedding abstraction (`ai/embedding.py`)

`EmbeddingProvider` is a `@runtime_checkable` Protocol with one method:
`async embed(texts) -> list[list[float]]`. `EmbeddingConfig(BaseSettings)` reads
`EMBEDDING_PROVIDER` (default `"berget"`), `EMBEDDING_MODEL` (default
`"intfloat/multilingual-e5-large"`), `BERGET_API_KEY`, and `LLM_BASE_URL` — one Berget
account/key covers both LLM and embedding calls. `create_embedding_provider()` lazy-imports
the concrete class so the heavy ML library loads only for the local provider and `openai`
only for the Berget provider.

- **`BergetEmbeddingProvider`** (default, `EMBEDDING_PROVIDER=berget`) — calls Berget's
  hosted `intfloat/multilingual-e5-large` via `openai.AsyncOpenAI.embeddings.create()`.
- **`LocalEmbeddingProvider`** (`EMBEDDING_PROVIDER=local`) — `sentence-transformers`
  in-process; the offline dev/test fallback.

See the [embedding hosting](/decisions/embedding-hosting.md) decision. The width
constraint and its startup verification (`verify_embedding_dimension`) are covered in
[embedding dimension](/decisions/embedding-dimension.md).

## Adding a new LLM use case

1. Add `YourRequest`/`YourResult` (`frozen=True`) to `ai/dtos.py`.
2. Add a `PromptTemplate` constant to `ai/prompts/_templates.py`.
3. Add a service function to `ai/services.py` (render the template, call
   `generate_structured`/`generate`/`generate_stream`).
4. Export from `__init__.py`.
5. Add a unit test mocking `ai.services.generate_structured`.
