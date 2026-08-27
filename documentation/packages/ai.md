---
type: Package
title: ai Package
description: Project-specific LLM logic — prompt templates, domain DTOs, service functions, per-task model selection, the embedding abstraction, and the LLM trace recorder.
resource: packages/ai
tags: [package, ai, prompts, embedding, llm]
timestamp: 2026-08-27T00:00:00Z
---

# ai Package (`packages/ai/`)

Project-specific LLM logic consuming [llm-core](/packages/llm-core.md). Knows about
Swedish legal documents; provides domain DTOs, prompt templates, service functions, and
the embedding abstraction. Depends on both `shared` and `llm-core`.

## Module layout

| Module | Role |
|---|---|
| `dtos.py` | All domain DTOs — frozen Pydantic v2 models for every LLM use case |
| `_observability.py` | `FileTraceRecorder`, `LLMTraceConfig`, `install_file_tracing()` — writes each LLM trace as its own local file |
| `_tracing_scope.py` | `interaction_scope()` / `agent_run_scope()` — the project's two correlation primitives, layered over llm-core's `trace_context`. See [Trace recording](#trace-recording-ai_observabilitypy) below |
| `services.py` | Six async service functions (below) |
| `llm_config.py` | Reads `llm_config.yaml` — document models, discovery, and role/embedding resolution |
| `embedding.py` | `EmbeddingProvider` Protocol, `create_embedding_provider` factory, `verify_embedding_dimension` |
| `tokenization.py` | Measures text in the embedding model's own tokens: `EmbeddingRuler`, `create_embedding_ruler()`, `verify_embedding_window()`, `SPECIAL_TOKEN_COUNT`. The only module that imports `transformers`. |
| `providers/openai_compatible_embeddings.py` | `OpenAiCompatibleEmbeddingProvider` — any OpenAI-compatible embeddings endpoint, Berget included; not the checked-in default, see below |
| `providers/local_embeddings.py` | `LocalEmbeddingProvider` — `sentence-transformers`, the checked-in default (`embedding.provider: local`) |
| `providers/roles.py` | `LLMRole` (the closed role set), `create_llm_provider(role)` (per-task model assignment, below) and `llm_role_is_disabled(role)` |
| `worker.py` | `worker_trace_scope(source)` — the `MessageScope` pipeline workers hand to `shared.worker.subscribe_step`, opening an `interaction_scope` around the message so its trace records land in a directory of their own; `close_llm_clients()` — the `StepTeardown` the four LLM-calling workers hand to the same call, releasing the loop-bound OpenAI-compatible client pool before their `asyncio.run()` loop closes (see [worker patterns](/pipeline/worker-patterns.md)) |
| `prompts/_renderer.py` | `PromptTemplate` frozen dataclass, `render()` free function, `render_tool_index(tools)` |
| `prompts/_templates.py` | The nine template constants |
| `__init__.py` | Public API — service functions, embedding types, and DTOs |

## Prompt templates (`ai/prompts/`)

`PromptTemplate` is a frozen dataclass holding just data (`name`, `system_prompt`,
`user_template`). The `name` is what identifies the prompt in a trace record — `render()`
returns a plain message list, so nothing downstream could otherwise tell which template
produced it. Rendering is a **free function** `render(template, context) ->
list[Message]` — it substitutes variables via `str.format_map(context)` and returns
`[Message(SYSTEM, system_prompt), Message(USER, rendered_user)]`. Ten template constants
cover every use case:

| Constant | Output format | User template variables |
|---|---|---|
| `QUERY_DECOMPOSITION` | JSON (`DecomposeResult` schema) | `{question}`, `{conversation_history}` |
| `QUERY_EXPANSION` | JSON (`QueryExpansionResult` schema) | `{question}`, `{max_variants}` |
| `ANSWER_SYNTHESIS` | Plain Swedish text with case citations | `{question}`, `{chunks}`, `{readings}`, `{tabular}`, `{annotations}`, `{gaps}`, `{conversation_history}` |
| `CHAT_PLAN` | Tool calls (no JSON schema) — English, direct replies in Swedish | `{question}`, `{today}`, `{conversation_history}`, `{tools}` |
| `CHAT_ORCHESTRATION` | Tool calls (no JSON schema) — English | `{plan}`, `{question}`, `{today}`, `{conversation_history}`, `{tools}` |
| `DECISION_READING` | JSON (`ReadingSelection` schema) | `{question}`, `{case_number}`, `{numbered_chunks}`, `{max_selected}`, `{max_summary_words}` |
| `METADATA_EXTRACTION` | JSON (`MetadataResult` schema) | `{raw_text}` |
| `ENTITY_EXTRACTION` | JSON (`EntityResult` schema) | `{raw_text}`, `{case_number}` |
| `DOCUMENT_SUMMARIZATION` | Plain Swedish text | `{raw_text}` |
| `TEXT_TO_SQL` | Plain text (tool loop, no JSON schema) | `{question}`, `{schema}`, `{tools}` |

`QUERY_EXPANSION`'s cap on variant count, `DECISION_READING`'s caps on selected-passage
count and summary length, and `TEXT_TO_SQL`'s schema block all live in the user
template, not the system prompt, for the same reason: `render()` only formats the
user template with `context`, so a `{max_variants}`, `{max_selected}` or `{schema}`
placeholder in the system prompt would reach the model verbatim instead of being
substituted.

`TEXT_TO_SQL` is rendered directly by [`agents.run_sql_agent`](/packages/agents.md) via
`render()`, not through a function in `ai/services.py` — the agent owns its own tool loop
(`llm_core.tool_loop`) rather than a single `generate`/`generate_structured` call, so there
is no service-layer wrapper for it to go through.

`CHAT_PLAN`, `CHAT_ORCHESTRATION` and `TEXT_TO_SQL` are the three prompts with a
`{tools}` block, and none spells its tools out by hand: `render_tool_index(tools)`
builds it from the same [`ToolDefinition`](/packages/llm-core.md)s each agent hands
`tool_loop`, one entry per tool — a signature line (`name(arg*, arg)`, `*` marking a
required argument, argument order following the schema's `properties`) followed by
the definition's `summary`. `CHAT_PLAN` is shown the executor's tools so its plan is
realistic, though `begin_research` is the only one it can call. The block lives in
the **user** template rather than the system prompt for all three, because `render()`
formats only the user template, and each of their system prompts embeds literal JSON
braces `str.format_map` would raise on. `render_tool_index` returns the entries
alone; the heading above them and the legend explaining `*` belong to each template,
in that template's language — which is what lets the Swedish `TEXT_TO_SQL` and the
English `CHAT_PLAN`/`CHAT_ORCHESTRATION` share one renderer.

All JSON-outputting templates embed the exact field schema in their system prompt, and
all prompts instruct the model to work in Swedish.

## Service functions (`ai/services.py`)

| Function | LLM call |
|---|---|
| `decompose_query(question, conversation_history=None, *, provider=None) -> DecomposeResult` — **no production caller**, see below | `generate_structured` |
| `expand_query(question, *, max_variants, provider=None) -> QueryExpansionResult` | `generate_structured` |
| `extract_metadata(raw_text, *, provider=None) -> MetadataResult` | `generate_structured` |
| `extract_entities(raw_text, case_number=None, *, provider=None) -> EntityResult` | `generate_structured` |
| `summarize_document(raw_text, *, provider=None) -> SummarizeResult` | `generate` |
| `synthesize_answer(request, *, provider=None) -> AsyncIterator[str]` | `generate_stream` |

`synthesize_answer` is an async generator (SSE critical path): it renders
`ANSWER_SYNTHESIS` and yields tokens without buffering. Its request carries an evidence
bundle, not just passages — `chunks`, `readings` (which passages of a decision a
reader selected, and how they connect — guidance, never itself a source, the same
status as an annotation), `tabular` (a SQL result with the query that produced it),
`annotations` (one `PassageNote` per selected passage: what it carries, and an
optional caution) and `gaps` (what the evidence does not reach) — and each section
renders as `(inget)` when empty, so an absent count reads as "not established"
rather than "not mentioned". `ANSWER_SYNTHESIS` states the readings rule
explicitly, alongside the annotations one it already had: never assert something
because a genomläsning says it, read it in the utdrag it names.
Passages are prefixed `[c3 · Mål {case_number}]`, and an appendix passage additionally
names itself as the appealed decision, because the model would otherwise present the
lower instance's words as the nämnd's own. The prompt asks the model to mark each claim
with the handle of the passage it rests on, directly after the sentence (`[c3]`,
adjacent markers `[c3][c7]` for a claim resting on several) — the same handle
`SourceReference` carries, which is what lets a client resolve the mark.

`CHAT_PLAN` and `CHAT_ORCHESTRATION` are written in English, alone among the prompts
here — both reason in English over Swedish input and Swedish tool results.
`CHAT_ORCHESTRATION`'s model calls tools carrying out a plan and never writes a word
the user reads; `CHAT_PLAN`'s model either calls `begin_research` with an English plan
for the executor, or replies to the user directly, in Swedish, when the message needs
no research. The Swedish prose an answered question gets is `ANSWER_SYNTHESIS`'s job.

`expand_query` is stateless by design — no conversation history, no filters, no
rewritten "best" query. It answers only "what else could this question have been
called," which is what keeps it a search-tool concern; see [query
expansion](/retrieval/query-expansion.md) for the full rationale.

`decompose_query` / `DecomposeResult` / `QUERY_DECOMPOSITION` have **no production
caller** since the [conversational agent](/retrieval/chat-agent.md) replaced the chat
pipeline that used them — the agent infers filters by calling tools instead. They are
still exported and tested; removing them is a decision nobody has taken yet.

## Domain DTOs (`ai/dtos.py`)

All DTOs are `frozen=True` Pydantic v2 models; consumers depend on them, so fields are not
removed or renamed.

| Domain | Request | Result |
|---|---|---|
| Query decomposition | `DecomposeRequest` | `DecomposeResult` (with `DateFilter`) |
| Query expansion | `QueryExpansionRequest` (`question`, `max_variants`) | `QueryExpansionResult` (`variants: list[str]` — alternative phrasings only, deliberately no filters and no rewritten "best" query) |
| Answer synthesis | `SynthesizeRequest` (with `ChunkContext`, `PassageNote`, `DecisionReading`, `TabularEvidence`) | streaming `str` tokens; `SourceCitation` for UI |
| Metadata extraction | `MetadataRequest` | `MetadataResult` |
| Entity & reference extraction | `EntityRequest` | `EntityResult` (with `ExtractedEntity`, `ExtractedReference`) |
| Summarization | `SummarizeRequest` | `SummarizeResult` |
| Embedding | `EmbedRequest` | `EmbedResult` |

`ChunkContext` carries only what the synthesis prompt actually renders: `chunk_text`,
`case_number`, `handle` (the executor's passage handle, e.g. `c3`, which the writer
marks a claim with), `section` and `appendix_label`. Nothing else: the writer quotes a
passage and attributes it, and grades nothing.

`DecisionReading` carries `handles` (the passages a reading selected, as ordinary
`c`-style handles already present in `chunks`) and `summary` (how those passages
connect, in Swedish) — never the decision's own text. The writer reads the named
passages from `chunks`; `summary` is guidance about where a finding lives, not the
finding itself.

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

`LLMRole` (a `StrEnum`: `STRUCTURED`, `SUMMARIZE`, `CHAT`, `ORCHESTRATE`, `SQL`, `READ`) is
the closed set code asks for. **The role set has two halves that must agree** — adding a
task needs both a new `LLMRole` member here and a matching entry under `roles:` in the
YAML; the enum is what turns a misspelled role into a type error instead of a runtime
`UnknownLLMRoleError`.

| Role | Used by | Default (Berget model) |
|---|---|---|
| `LLMRole.STRUCTURED` | `expand_query`, `extract_metadata`, `extract_entities` | `mistralai/Mistral-Small-3.2-24B-Instruct-2506` |
| `LLMRole.SUMMARIZE` | `summarize_document` | `google/gemma-4-31B-it` |
| `LLMRole.CHAT` | `synthesize_answer`, and the [conversational agent's](/retrieval/chat-agent.md) plan step | `zai-org/GLM-5.2` |
| `LLMRole.ORCHESTRATE` | The conversational agent's executor tool loop | `openai/gpt-oss-120b` |
| `LLMRole.READ` | The conversational agent's document-reading sub-agent | `openai/gpt-oss-120b` |
| `LLMRole.SQL` | [`agents.run_sql_agent`](/packages/agents.md) | `openai/gpt-oss-120b` |

`create_llm_provider(role: LLMRole, document=None)` is the single function every
composition root calls — there is no per-role delegate. Requesting a role the YAML does
not declare raises `UnknownLLMRoleError`; `resolve_role_config`, one layer below, still
takes a plain `str` because it resolves an arbitrary file key, but `LLMRole` is what call
sites pass.

Each composition root constructs the role-appropriate provider(s) once at startup and
threads them into the call sites via the `provider=` keyword — no hidden global default
in production.

`llm_role_is_disabled(role, document=None)` answers whether the YAML assigns a role
`kind: none` — no model at all — without building anything. It is for the callers that
have a genuine no-model path and want to choose it at startup:
[worker-extract](/pipeline/extract.md) is the only one today. Everything else builds the
provider and lets it refuse, since constructing a `none` provider always succeeds and
raises `LLMDisabledError` at the call that wanted a model. See
[running with no LLM](/reference/llm-config.md).

**Gemini caveat.** The defaults above are Berget model IDs and will not resolve against
Gemini's API, so pointing a role at `provider: gemini` means changing its `model:` in the
same edit (e.g. `gemini-2.5-flash-lite`, since `gemini-2.0-flash` was shut down — see
[LLM pricing](/reference/llm-pricing.md)).

## Embedding abstraction (`ai/embedding.py`)

`EmbeddingProvider` is a `@runtime_checkable` Protocol with one method:
`async embed(texts) -> list[list[float]]`. `EmbeddingConfig` is defined in
`ai/llm_config.py` (and re-exported here) and carries `provider` (an `EmbeddingBackend`),
`model`, `dimension`, `api_key` and `base_url`, resolved from `llm_config.yaml`'s
`embedding:` block — the base URL and key variable come from the same `providers:` entry
the LLM roles use, so one Berget account/key covers both. `create_embedding_provider()`
dispatches on the resolved backend (`local`, or `openai_compatible`) and lazy-imports the
concrete class, so the heavy ML library loads only for the local provider and `openai`
only for the hosted one; there is no fallback `case`, since a host whose kind has no
embeddings client is already rejected earlier, by `resolve_embedding_config`.

`EmbeddingBackend` (`local`, `openai_compatible`) is deliberately a subset of
`llm_core.ProviderKind` plus `LOCAL` — its `OPENAI_COMPATIBLE` member takes its value
*from* `ProviderKind.OPENAI_COMPATIBLE` so the two vocabularies cannot drift apart. Not
every `ProviderKind` has an embeddings client wired up here: naming a provider whose
`kind` is `gemini` under `embedding.provider` raises
`ai.errors.UnsupportedEmbeddingBackendError` from `resolve_embedding_config`, at
config-resolution time rather than at the first embed call, naming the offending YAML
key.

`verify_embedding_dimension(provider, config=None)` is the startup guard. It checks
**three** declarations of the width against each other — `embedding.dimension` in the
YAML, `shared.config.EMBEDDING_DIMENSION`, and the width the model actually produces for
a probe string — and raises `EmbeddingDimensionMismatchError` naming the disagreement.
See [embedding dimension](/decisions/embedding-dimension.md).

`get_embedding_prefixes()` returns the `(query, passage)` pair for the configured model.
Both sides come from one place so they cannot drift apart; the query half is used by the
[retrieval agent](/retrieval/chat-agent.md) and the passage half by
[worker-embed](/pipeline/embed.md).

- **`OpenAiCompatibleEmbeddingProvider`** (`embedding.provider: berget` in
  `llm_config.yaml`; the checked-in config actually ships `local`, below) — calls
  Berget's hosted `intfloat/multilingual-e5-large` via
  `openai.AsyncOpenAI.embeddings.create()`. `__init__` validates `api_key` and
  `base_url` (raising `ai.errors.MissingApiKeyError` if the key is missing) but does
  not build the client — each `embed()` call fetches one from
  `llm_core.get_async_openai()`, bound to the loop it is running on, rather than
  holding one built at construction; see [loop-bound
  clients](/packages/llm-core.md#loop-bound-clients-_clientspy). **Traced**: embedding
  runs once per chunk over the whole corpus, so it is plausibly the largest single line
  of token spend.
- **`LocalEmbeddingProvider`** (`embedding.provider: local` — the default in this
  repo's checked-in `llm_config.yaml`, or `EMBEDDING_PROVIDER=local`) —
  `sentence-transformers` in-process; the offline dev/test fallback. **Not traced** — no
  API call, no token accounting, and a contribution of exactly zero to what a question
  cost.

Tracing sits inside `OpenAiCompatibleEmbeddingProvider` rather than in a wrapper: a
wrapper implementing `EmbeddingProvider` could time the call but not see token usage,
since `embed() -> list[list[float]]` has nowhere to put it. The embedded texts are not
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

## Token budgeting (`ai/tokenization.py`)

Measures text in the embedding model's own tokens — the question that decides whether a
chunk survives embedding intact, which a general-purpose tokenizer (tiktoken) does not
answer. `EmbeddingRuler` is a frozen dataclass carrying `count_tokens`
(`Callable[[str], int]`, content tokens only — no special tokens) and
`max_sequence_tokens`. `create_embedding_ruler(config=None)` loads
`transformers.AutoTokenizer.from_pretrained(embedding.model)` (`@lru_cache`d, since
`scripts/run_pipeline.py` composes the chunk and embed workers into one process) and
observes the window from `tokenizer.model_max_length`. `from_pretrained` answers `None`
for a model name it cannot resolve to a tokenizer class rather than raising, so the
loader checks for that and raises `TokenizerUnavailableError` naming the model —
otherwise the `None` travels as far as the first `count_tokens` call and surfaces as an
unrelated `AttributeError` after the chunk worker has already started. `verify_embedding_window(ruler, *,
reserved_tokens)` is the startup guard: it rejects a non-positive window, a window at or
above the `int(1e30)` sentinel `transformers` reports for a tokenizer config missing
`model_max_length`, and a window too small for the caller's fixed overhead, raising
`EmbeddingWindowError` in each case. `SPECIAL_TOKEN_COUNT = 2` is the `<s>`/`</s>` pair an
XLM-R-style tokenizer wraps around one encoded input — added once by the caller
composing several pieces, not once per piece.

`EmbeddingRuler` is a value carrying a callable rather than a Protocol with an
implementation behind it, deliberately: a fake for tests is a lambda, so nothing needs
patching and no unit test risks importing `transformers` (and with it torch). See
[testing](/testing.md).

Consumed by [worker-chunk](/pipeline/chunk.md) (deriving its chunk token budget) and
[worker-embed](/pipeline/embed.md) (the input-length warning). Full rationale — why the
window is observed rather than declared, and the budget arithmetic it feeds — is in
[embedding window](/decisions/embedding-window.md).

`transformers` is a **direct** dependency of this package (`packages/ai/pyproject.toml`),
same story as the existing `numpy` entry: it already arrives transitively via
`sentence-transformers`, but `ai/tokenization.py` imports it directly, so it is declared
directly. No upper bound is pinned here — the Intel Mac `transformers<5` ceiling lives in
the root `pyproject.toml`, and a second ceiling here would only fight it.

## Trace recording (`ai/_observability.py`)

`ai` supplies the concrete recorder behind llm-core's hook. It belongs here because it
needs llm-core's record type, and `shared` must not depend on llm-core.

`install_file_tracing(root=None, config=None)` is called **once at startup** by every
process that makes LLM calls — the API lifespan and each of the four LLM workers. It
takes no storage backend: traces never went through `shared`'s `StorageBackend`, and
now nothing in this module imports it. It never raises: a trace root it cannot create
leaves no recorder at all, and llm-core treats that as tracing off. `trace_context` is
re-exported here so callers need no direct llm-core dependency.

The recorder owns the **storage layout** — one JSON file per billed call, under
`{LOCAL_STORAGE_PATH}/{LLM_TRACE_KEY_PREFIX}/{date}/{interaction_id}/`, so the
directory a record lands in is the correlation index and no reader script has to
reconstruct it. Each write is synchronous and whole-file — written to a `.tmp` name,
then `os.replace`d into place — which puts a file write ahead of the next LLM call.
On local disk that costs microseconds; it would be the wrong trade over a network
filesystem or an object store, which is the condition under which buffering onto a
background writer should come back. See [LLM Observability](/observability.md) for the
full layout and the correlation table.

Cost is **not** written into the record, and there is no rate table in this package.
A record carries the served `model` and the provider's `usage`, which is the complete
raw material — applying a price to it is an analysis question, answered against
[LLM pricing](/reference/llm-pricing.md) when the traces are analyzed. Computing it here
would only freeze a rate that may be wrong or, as today, missing: no Berget rate is
published in this repo, so every record would carry a null that could never be filled
in.

### Correlation (`ai/_tracing_scope.py`)

`interaction_scope(interaction_id=None, **values)` and `agent_run_scope(**values)` sit
next to `worker_trace_scope` for the same reason: `trace_context` itself carries an
opaque mapping and llm-core deliberately gives no key a meaning, but `interaction_id`
and `agent_run_id` are project concepts, so the module that gives them one lives in `ai`,
not `llm-core`.

`interaction_scope` is what lets a sub-agent join its caller's interaction instead of
starting a separate one: an explicit id wins, else an id already in the trace context is
**inherited**, else one is **minted**. `agent_run_scope` always mints, which is what
still tells two invocations of the same sub-agent apart inside one interaction. Both are
re-exported from `ai.__init__`. Full mechanics, the call sites that use them, and the
`X-Interaction-Id` header they back: [LLM Observability](/observability.md).

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
