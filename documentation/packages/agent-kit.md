---
type: Package
title: agent-kit Package
description: The domain-free agent core — the prompt renderer, LLM role/provider config, file trace recorder and correlation scopes, the per-conversation context store, the streaming synthesis step, cross-turn scratchpad persistence, and the run_agent plan→execute→synthesize orchestrator; depends only on llm-core plus pydantic/pyyaml, and is consumed by ai and agents.
resource: packages/agent-kit
tags: [package, agent-kit, orchestrator, llm, context, scratchpad]
timestamp: 2026-08-30T00:00:00Z
---

# agent-kit Package (`packages/agent-kit/`)

Everything a plan-then-execute-then-synthesize agent needs that is not specific
to any one corpus or language. It depends only on
[llm-core](/packages/llm-core.md) (the provider abstraction and the tool loop)
plus pydantic, pydantic-settings and pyyaml — nothing from `shared`, `ai`,
`agents` or `api`. The domain (Swedish prompts, evidence DTOs, the chat
toolset) lives in those packages and consumes this one, never the other way
round: this is the piece meant to be lifted whole into a different agent
project.

## Module layout

| Module | Role |
|---|---|
| `orchestrator/` | `run_agent(...)` — the generic three-phase orchestrator — plus its event types and the `PlanPhase`/`ExecutionPhase` DTOs |
| `synthesis/` | `synthesize(template, context, ...)` — the generic streaming answer step |
| `context/` | `ContextStore` Protocol, `InMemoryContextStore`, `JsonBlob` — the per-conversation carry-over |
| `prompts/` | `PromptTemplate`, `render`, `render_tool_index` — the renderer, moved verbatim from `ai.prompts._renderer` |
| `config/` | The LLM role/provider YAML loader and resolver — `create_llm_provider(role: str)`, `resolve_role_config`, `get_llm_config`, `load_config_document`, `LLMConfigDocument`, the precedence helpers |
| `tracing/` | `FileTraceRecorder`/`install_file_tracing` (trace root injected by the caller) and the `interaction_scope`/`agent_run_scope` correlation scopes |
| `errors.py` | `AgentKitError` base, plus the `LLMConfig*` error family |

## `run_agent`: plan → execute → synthesize

`run_agent(request, *, tools, executors, evidence, plan, execution, synthesize, plan_provider=None, executor_provider=None, source="agent", context_store=None, conversation_id=None, scratchpad=None, scratchpad_codec=None)`
is the orchestrator every host configures rather than reimplements. Three
phases:

1. **Plan.** One call on `plan_provider`, wrapped in `run_tool_loop` with the
   host's single `plan.plan_tool` and `max_iterations=1`. Before this call, a
   restored `scratchpad` (see below) is ready for `plan.build_messages` to read
   its shorthand from; `plan.read_plan` reads the terminal message back into a
   strategy string, or `None` when the model replied directly. A direct reply
   short-circuits the run: `PlanReplyEvent`, the pad persisted, `DoneEvent` —
   no executor loop, no synthesis call.
2. **Execute.** The host's `tool_loop` (`execution.build_messages`, `tools`,
   `executors`, `execution.terminal_tools`, `execution.max_iterations`,
   `scratchpad`) runs on `executor_provider`, which falls back to
   `plan_provider` when unset so a single-model run works. Each
   `ToolCallStarted`/`ToolCallFinished` becomes a generic
   `ToolCallEvent`/`ToolResultEvent`; a tool result carrying an `error` key maps
   to `ToolStatus.REFUSED` when `refused` is true, else `ToolStatus.ERROR`.
3. **Synthesize.** `evidence` — the host's own object, populated by its
   executor closures, never touched by the orchestrator itself — is surfaced
   once as an `EvidenceEvent` before the host's `synthesize(request, evidence)`
   streams `TokenEvent`s. `evidence` is usually the same object passed as
   `scratchpad`; they are separate parameters because `evidence` is opaque
   (`E`) while the pad must be typed for the board and persistence.

Every phase failure funnels to one `ErrorEvent` (message
`"The request could not be completed."`) and ends the stream; an `ErrorEvent`
is never followed by a `DoneEvent`. The whole call runs inside one
`interaction_scope(source=source, prompt=execution.prompt_name)` plus one
`agent_run_scope()`, opened by the orchestrator itself — a host names its
`source` and both scopes exist without the host importing `tracing` directly.

`AgentRequest` is a `@runtime_checkable` Protocol (`question: str`,
`history: list[dict]`, read-only) — a host's own frozen request model
satisfies it structurally, with no import from `agent_kit` needed on the host
type itself.

## The context store

`ContextStore` is a two-method Protocol — `get(conversation_id) -> JsonBlob`,
`set(conversation_id, blob) -> None` — where `JsonBlob = dict[str, Any]`. It is
the pluggable storage backend a scratchpad's carry-over is written through;
`run_agent` never opens a database connection or decides what the blob holds.
`InMemoryContextStore` is the dict-backed implementation for tests, scripts and
single-process runs; it copies on the way in and out so a caller mutating a
blob it received cannot reach back into the store.

A host durable-backs `ContextStore` with its own storage — see
[`PostgresContextStore`](/data-model/sessions.md) for the concrete
implementation this project wires the chat endpoint through.

## Scratchpad persistence: cross-turn recall

A [`Scratchpad`](/packages/llm-core.md#scratchpad-working-memory) — llm-core's
generic, keyed working-memory — is a turn's evidence: a host's executors write
it, `execution`'s `tool_loop` boards its previews every iteration, and the
host's `synthesize` reads it directly. `run_agent` optionally makes that same
pad recall across turns, given four things together: `context_store`,
`conversation_id`, `scratchpad` and `scratchpad_codec`
(`ScratchpadCodec[V]` — `encode`, `decode`, `cap`, the *only* domain hook in
the whole mechanism, dispatched on an entry's key however the host likes).
When all four are given, `run_agent`:

1. Restores the pad from the store (`blob.get("scratchpad", {})`, via
   `scratchpad_codec.decode`) before the plan call, so `plan.build_messages`
   can show the planner the restored pad's shorthand — the *only* place a
   host's plan step sees carried-over state, since the plan is what decides
   whether a turn needs research at all.
2. Threads the same pad into the execute-phase `tool_loop`, so its board keeps
   growing across restored and newly-gathered entries alike.
3. Persists the whole pad — `{"scratchpad": scratchpad.dump(codec.encode,
   cap=codec.cap)}` — via `context_store.set`, once after a direct reply, once
   after synthesis completes on a researched turn. `cap` bounds how many heavy
   (previewed) entries survive a turn, newest-wins; a small "K=V" entry is
   exempt and always carries forward.

Any subset short of all four leaves the pad turn-scoped only: no restore, no
persistence, and `run_agent` behaves exactly as it does with no `scratchpad`
at all. What the pad's entries mean is entirely the host's choice — this layer
only restores, boards and persists it.

## Prompt rendering (`prompts/`)

`PromptTemplate` (`name`, `system_prompt`, `user_template`), `render(template,
context) -> list[Message]` and `render_tool_index(tools)` are unchanged from
their prior home in `ai.prompts._renderer` — every domain template still
renders through this module, imported via `ai.prompts` or directly from
`agent_kit.prompts`.

## LLM role/provider config (`config/`)

The provider/role half of a project's `llm_config.yaml` — declaring providers,
assigning a model per task role, and the environment-wins precedence — lives
here as domain-free machinery: `role` is a plain `str` naming a key in the
file, not a closed enum, since agent-kit has no opinion on what tasks a host
declares. A host that wants a misspelled role to be a type error keeps its own
`StrEnum` of role names one layer up and passes its members in — a `StrEnum`
member is a `str`, so it flows through unchanged (see
[`LLMRole`](/packages/ai.md#per-task-model-selection-aiprovidersrolespy)).

`LLMConfigDocument` carries an `embedding:` block as an **opaque passthrough**
— agent-kit has no opinion on embeddings, so it validates everything else in
the file (`providers`, `defaults`, `roles`) and leaves `embedding` for the host
to validate against its own shape. See
[llm_config.yaml](/reference/llm-config.md) for the full contract and
[ai](/packages/ai.md) for the embedding half.

`create_llm_provider(role, document=None)` raises `UnknownLLMRoleError` for an
undeclared role; `llm_role_is_disabled(role, document=None)` answers whether
the file assigns `role` a `kind: none` provider without building anything.

## Tracing (`tracing/`)

`FileTraceRecorder` writes one JSON file per billed call under an **injected**
root — `install_file_tracing(root=None, config=None)` takes no opinion on
*where* traces live, only on the layout beneath that root:
`{root}/{date}/{interaction_id}/{time}-{source}-{id}.json`. A host that wants
traces beside its own local data — this project keeps them under
`StorageSettings().local_storage_path` — supplies `root` explicitly; see
[`ai.install_file_tracing`](/packages/ai.md), a thin wrapper that does exactly
that so the on-disk path a reader already expects does not move. Full record
schema, correlation keys and the wiring invariant: [LLM
Observability](/observability.md).

`interaction_scope`/`agent_run_scope` are the same correlation primitives
described there — an explicit id wins, else one already in the trace context
is inherited (`interaction_scope`), else one is minted; `agent_run_scope`
always mints. They live here because `run_agent` opens both itself; a host
that opens its own scope around a non-`run_agent` call (`agents.run_sql_agent`
does, directly) imports them from here too, ordinarily via `ai`'s re-export.

## Errors (`errors.py`)

`AgentKitError` is the package's base. `LLMConfigError` (and its
`LLMConfigNotFoundError`/`LLMConfigInvalidError` subclasses) and
`UnknownLLMRoleError` subclass it — a host that re-exports them (`ai.errors`
does, for its existing call sites) is re-exporting agent-kit's own hierarchy,
not a project-specific one.

## Tests

`packages/agent-kit/tests/unit/test_run_agent.py` exercises the orchestrator
end to end against scripted providers and a fake toolset: both endings of the
plan step, the executor loop's event mapping, the error funnel for each of the
three phases, and the scratchpad round trip (the pad restored from the store
before planning, threaded into the execute-phase `tool_loop`, and persisted via
the codec on both a direct reply and a researched turn). `test_context_store.py`
covers `InMemoryContextStore`'s copy-on-read and copy-on-write behaviour.
