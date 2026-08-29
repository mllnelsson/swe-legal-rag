# agent-kit

The domain-free core of a conversational agent. Everything a
plan → execute → synthesize agent needs that is *not* specific to one corpus or
language: the LLM role/provider config, the orchestrator, the streaming
synthesis step, per-conversation carry-over, the file trace recorder and the
correlation scopes.

It depends only on [`llm-core`](../llm-core/README.md) plus `pydantic` and
`pyyaml`. **It imports nothing from `shared`, `ai`, `agents` or `api`** — the
domain lives in those and consumes this, never the other way round. That boundary
is the whole point: this is the package you lift into your next agent project.

- **What you get, and the seams you fill:** [Mental model](#mental-model)
- **Copying it out:** [Copy-paste checklist](#copy-paste-checklist)
- **A full example:** [Chat with your database over multiple messages](#worked-example-chat-with-your-database)

---

## Mental model

A turn runs in three phases, and the split is deliberate — it puts the strong
model where the reasoning is hard and a smaller one where the work is mechanical.

```
                  carry-over blob (from earlier turns)
                          │
   question ──►  ┌────────▼────────┐   direct reply?  ──► answer, done
                 │  1. PLAN        │   (greeting, a follow-up
                 │  strong model   │    the history answers)
                 └────────┬────────┘
                       strategy
                          │
                 ┌────────▼────────┐
                 │  2. EXECUTE     │   your tools gather evidence,
                 │  smaller model  │   ending on a terminal tool
                 └────────┬────────┘
                    evidence object
                          │
                 ┌────────▼────────┐
                 │  3. SYNTHESIZE  │   stream the answer from the
                 │  strong model   │   evidence, sent once
                 └─────────────────┘
```

`run_agent` owns that control flow, the tracing scopes, the error funnel and the
carry-over thread — and **nothing domain-specific**. Everything about *your* app
arrives through arguments:

| Seam | What you supply | Type |
| --- | --- | --- |
| `request` | the question + prior turns | anything with `.question: str` and `.history: list[dict]` (the `AgentRequest` Protocol) |
| `tools` / `executors` | your tools and the async functions behind them | `list[ToolDefinition]`, `dict[str, ToolExecutor]` |
| `evidence` | a mutable object your executors fill in | any type `E` you choose |
| `plan` | the plan prompt, the plan-signal tool, how to read the plan back | `PlanPhase` |
| `execution` | the executor prompt, the terminal tools, the iteration budget | `ExecutionPhase` |
| `synthesize` | turn the filled-in evidence into a stream of answer tokens | `async (request, evidence) -> AsyncIterator[str]` |
| `context_store` + `derive_context` | *(optional)* multi-message carry-over | `ContextStore`, a derive function |

The orchestrator never sees a field name of yours. It holds `evidence` as an
opaque handle, hands it to `synthesize`, and surfaces it once as an
`EvidenceEvent` — so **the way evidence flows is: your executors mutate a shared
object, and your `synthesize` reads it back**. Keep that picture; the worked
example below is nothing more than a concrete instance of it.

### The event stream

`run_agent` never raises for a question it cannot answer — it yields a stream that
always ends in `DoneEvent` or `ErrorEvent` (never both):

`PlanReplyEvent(text)` · `ToolCallEvent(id, name, arguments)` ·
`ToolResultEvent(id, name, arguments, status, result)` · `EvidenceEvent(evidence)`
· `TokenEvent(text)` · `DoneEvent()` · `ErrorEvent(message)`

These carry no vocabulary of your corpus. A host maps them onto its own richer
wire events (labels, citations, a SQL trail) as it consumes the stream — see how
`agents/chat/_agent.py` in this repo does exactly that.

---

## Copy-paste checklist

This is the "what do I actually have to do" list.

1. **Bring two packages, not one.** Copy `packages/agent-kit/` *and*
   `packages/llm-core/`. agent-kit's `pyproject.toml` declares
   `llm-core = { workspace = true }`; keep them both as uv workspace members in
   the new repo, or repoint that source.

2. **Bring the runtime deps.** agent-kit needs `pydantic`, `pydantic-settings`,
   `pyyaml`; llm-core needs `openai` and `google-genai`. All are on PyPI.

3. **Add an `llm_config.yaml`** at the new repo root (or point `LLM_CONFIG_PATH`
   at one). Copy [this repo's](../../llm_config.yaml) as a starting point and
   **delete the `embedding:` block** — agent-kit tolerates it but has no use for
   it. Declare your providers and one `role:` per model you want. See
   [config reference](#configuration) below.

4. **Set the keys.** Each provider names an env var (`api_key_env`); put the value
   in `.env` / your secret manager. Never in the YAML.

5. **Wire startup once** — install tracing, build providers:

   ```python
   from pathlib import Path
   from agent_kit import install_file_tracing, create_llm_provider

   install_file_tracing(Path("./llm-traces"))   # once per process
   plan_provider = create_llm_provider("chat")        # a role from the YAML
   executor_provider = create_llm_provider("orchestrate")
   ```

6. **Fill the seams** for your domain — the request type, the tools/executors, the
   evidence object, the two prompts, and `synthesize`. That is the work, and the
   [worked example](#worked-example-chat-with-your-database) does all of it.

7. *(For follow-up conversations)* **back a `ContextStore`** — `InMemoryContextStore`
   is built in; a durable one is a ~15-line class (shown below).

What you do **not** touch: the orchestrator, the tracing, the config loader, the
prompt renderer, the tool loop. That is the reusable core.

> **Naming note.** `agent_kit.synthesize` (a helper that renders a template and
> streams) and `run_agent(..., synthesize=…)` (the callable *you* pass) share a
> name. The helper is one convenient way to *implement* the callable — see the
> example — but you can implement the callable however you like.

---

## Worked example: chat with your database

You have a database in another project and you want to *chat* with it — ask
questions in natural language, get answers, over multiple messages that build on
each other. Here is the whole thing on agent-kit. (SQL execution is stubbed as
`run_query`; swap in your driver.)

### 1. The config file — `llm_config.yaml`

```yaml
version: 1
providers:
  openai:
    kind: openai_compatible
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
defaults:
  provider: openai
  temperature: 0.0
roles:
  chat:                       # strong model: plans the turn, writes the answer
    model: gpt-4o
  orchestrate:                # cheaper model: runs the tool loop
    model: gpt-4o-mini
```

### 2. The request type

Any object with `question` and `history` satisfies the `AgentRequest` Protocol.
Add `conversation_id` so turns can find their carry-over.

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class DbChatRequest:
    question: str
    conversation_id: str
    history: list[dict] = field(default_factory=list)   # [{"role", "content"}, …]
```

### 3. The evidence object + the tools that fill it

`evidence` is a plain mutable object. The executors close over one instance and
write into it; `synthesize` reads it back.

```python
from dataclasses import dataclass, field
from typing import Any
from llm_core import ToolDefinition

@dataclass
class DbEvidence:
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)

RUN_SQL = ToolDefinition(
    name="run_sql",
    summary="run a read-only SQL query and see the rows",
    description=(
        "Execute one read-only SQL query against the analytics database and get "
        "the columns and rows back. Call it as many times as you need to refine."
    ),
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
ANSWER = ToolDefinition(
    name="answer",
    summary="finish: you have the rows the question needs",
    description="Call once the query results answer the question.",
    parameters={"type": "object", "properties": {}},
)

def build_tools(evidence: DbEvidence):
    async def run_sql(query: str) -> dict:
        if not query.lower().lstrip().startswith("select"):
            # The decline convention: refuse without raising; the loop repairs.
            return {"error": "only read-only SELECT queries are allowed",
                    "refused": True}
        columns, rows = await run_query(query)          # your driver here
        evidence.sql, evidence.columns, evidence.rows = query, columns, rows
        return {"row_count": len(rows), "columns": columns}

    async def answer(**_kwargs) -> dict:
        return {"ok": True}

    return [RUN_SQL, ANSWER], {"run_sql": run_sql, "answer": answer}
```

### 4. The two prompts

`PromptTemplate` is inert data; `render` turns it into messages, and
`render_tool_index` writes the tool list into the prompt so it can never name an
argument your schema lacks.

```python
from agent_kit import PromptTemplate

PLAN = PromptTemplate(
    name="db_chat_plan",
    system_prompt=(
        "You help a user query an analytics database. Read the question. If it "
        "is small talk or already answered by the history, reply directly. "
        "Otherwise call begin_research with a one-line plan."
    ),
    user_template=(
        "Question: {question}\n\nConversation so far:\n{history}\n\n"
        "What we already know this conversation:\n{context}\n\n"
        "Tools the executor holds:\n{tools}"
    ),
)
EXEC = PromptTemplate(
    name="db_chat_exec",
    system_prompt=(
        "Carry out the plan by querying the database. Inspect the schema with "
        "small queries first if unsure. Call answer once the rows are in hand."
    ),
    user_template="Question: {question}\n\nPlan: {plan}\n\nTools:\n{tools}",
)
SYNTH = PromptTemplate(
    name="db_chat_answer",
    system_prompt="Answer the question in plain prose, grounded only in the rows.",
    user_template="Question: {question}\n\nSQL: {sql}\n\nRows:\n{rows}",
)
```

### 5. The plan phase and the execution phase

```python
import json
from agent_kit import PlanPhase, ExecutionPhase, render, render_tool_index
from llm_core import Message, ToolDefinition

BEGIN_RESEARCH = ToolDefinition(
    name="begin_research",
    summary="hand a plan to the executor",
    description="Call once to begin. Pass a short plan; the executor carries it out.",
    parameters={
        "type": "object",
        "properties": {"plan": {"type": "string"}},
        "required": ["plan"],
    },
)

def read_plan(message: Message) -> str | None:
    # A begin_research call means "research this"; the plan rides on its args.
    # No tool call means the model replied directly — there is no plan to run.
    for call in message.tool_calls:
        if call.name == "begin_research":
            return call.arguments.get("plan", "")
    return None

def _history(history: list[dict]) -> str:
    return "\n".join(f"{e['role']}: {e['content']}" for e in history) or "(none)"

plan = PlanPhase(
    build_messages=lambda req, tools, blob: render(PLAN, {
        "question": req.question,
        "history": _history(req.history),
        "context": json.dumps(blob, ensure_ascii=False),   # carry-over, {} on turn 1
        "tools": render_tool_index(tools),
    }),
    plan_tool=BEGIN_RESEARCH,
    read_plan=read_plan,
    prompt_name=PLAN.name,
    source="db_chat.plan",
)
execution = ExecutionPhase(
    build_messages=lambda req, tools, strategy: render(EXEC, {
        "question": req.question,
        "plan": strategy,
        "tools": render_tool_index(tools),
    }),
    terminal_tools={"answer"},
    max_iterations=6,
    prompt_name=EXEC.name,
)
```

### 6. Synthesis

The callable `run_agent` invokes after the loop. Here it uses the
`agent_kit.synthesize` helper to render `SYNTH` and stream it — and it says the
honest thing when the executor found nothing:

```python
from collections.abc import AsyncIterator
from agent_kit import synthesize as synth_stream

def make_synthesize(provider):
    async def synthesize(req, evidence: DbEvidence) -> AsyncIterator[str]:
        if not evidence.rows:
            yield "I couldn't find anything in the database that answers that."
            return
        rows = "\n".join(str(r) for r in evidence.rows[:50])
        async for token in synth_stream(
            SYNTH,
            {"question": req.question, "sql": evidence.sql or "", "rows": rows},
            provider=provider,
            source="db_chat.answer",
        ):
            yield token
    return synthesize
```

### 7. Multi-message: the carry-over

This is the part that makes it a *conversation*. A `ContextStore` holds one JSON
blob per `conversation_id`; the orchestrator injects it into the plan call every
turn, and `derive_context` decides what the finished turn leaves behind. Here we
accumulate the tables the conversation has already touched, so a follow-up doesn't
re-discover the schema:

```python
from agent_kit import InMemoryContextStore, JsonBlob

store = InMemoryContextStore()          # swap for a durable one in production

def derive_context(blob: JsonBlob, request, evidence: DbEvidence) -> JsonBlob:
    asked = list(blob.get("questions_answered", []))
    if evidence.rows:
        asked.append(request.question)
    return {"questions_answered": asked[-10:]}   # keep it small
```

A **durable** store is the same Protocol backed by your DB — two async methods:

```python
class PostgresContextStore:
    def __init__(self, pool): self._pool = pool
    async def get(self, conversation_id: str) -> JsonBlob:
        row = await self._pool.fetchrow(
            "select context from sessions where id = $1", conversation_id)
        return (row and row["context"]) or {}
    async def set(self, conversation_id: str, blob: JsonBlob) -> None:
        await self._pool.execute(
            "update sessions set context = $1 where id = $2", blob, conversation_id)
```

> `agents/chat` in this repo wires a real `PostgresContextStore` against a
> `sessions.context` JSONB column (migration 007) — a working reference for the
> durable path.

### 8. Drive it

```python
from agent_kit import (
    install_file_tracing, create_llm_provider, run_agent,
    PlanReplyEvent, ToolResultEvent, EvidenceEvent, TokenEvent,
    DoneEvent, ErrorEvent,
)

install_file_tracing()                                   # once, at startup
plan_provider = create_llm_provider("chat")
executor_provider = create_llm_provider("orchestrate")

async def ask(request: DbChatRequest) -> None:
    evidence = DbEvidence()
    tools, executors = build_tools(evidence)

    async for event in run_agent(
        request,
        tools=tools,
        executors=executors,
        evidence=evidence,
        plan=plan,
        execution=execution,
        synthesize=make_synthesize(plan_provider),
        plan_provider=plan_provider,
        executor_provider=executor_provider,   # falls back to plan_provider if unset
        source="db_chat",
        context_store=store,
        conversation_id=request.conversation_id,
        derive_context=derive_context,
    ):
        match event:
            case PlanReplyEvent(text=t) | TokenEvent(text=t):
                print(t, end="", flush=True)          # stream to the user
            case ToolResultEvent(name=n, status=s):
                log.info("tool %s -> %s", n, s)       # progress for a UI
            case EvidenceEvent(evidence=ev):
                render_the_sql_panel(ev)              # citations, before prose
            case ErrorEvent(message=m):
                print(f"\n[error] {m}")
            case DoneEvent():
                print()
```

Call `ask` again with the same `conversation_id` and a new question, and turn two
starts with turn one's carry-over already in front of the planner. That is the
multi-message loop, with nothing added.

---

## Configuration

`llm_config.yaml` (or `LLM_CONFIG_PATH`) is the source of truth for which model
and provider each task uses. Add a `role:` and call
`create_llm_provider("<role>")` — no code change introduces a model.

**Precedence** (highest first): environment variable → the role's entry →
`defaults` → the field default. So the file is the checked-in default and the
environment is the deployment override:

- `LLM_MODEL_<ROLE>` overrides one role's model (e.g. `LLM_MODEL_CHAT`).
- `LLM_PROVIDER`, `LLM_MODEL`, etc. are process-wide overrides — a stale one in
  `.env` flattens every role onto one host (the loader warns when it does).
- API keys are **never** in the file: a provider names its `api_key_env`.

A `kind: none` provider (or `LLM_PROVIDER=none`) disables a role — it builds
without keys and raises `LLMDisabledError` only if something calls it. That is how
a process that makes no LLM calls runs with nothing configured.

## Observability

`install_file_tracing(root)` writes one JSON file per billed LLM call, laid out as
`{root}/{date}/{interaction_id}/{time}-{source}-{id}.json` — one directory per
turn, so "what did this request cost" is a sum over one folder. Prompts and
responses are stored whole; cost is deliberately **not** computed (the record
carries `model` and `usage`; pricing is an analysis step).

The wiring invariant: **every process that makes LLM calls calls
`install_file_tracing()` once at startup.** `run_agent` sets the per-turn and
per-phase `source`/`prompt` scopes for you; if you make a provider call *outside*
the orchestrator, wrap it in `llm_core.traced_call` so it lands in the same tree.

## Public API

Everything below is exported from the top-level `agent_kit` namespace.

| Group | Names |
| --- | --- |
| Orchestrator | `run_agent`, `AgentRequest`, `PlanPhase`, `ExecutionPhase` |
| Events | `AgentEvent`, `PlanReplyEvent`, `ToolCallEvent`, `ToolResultEvent`, `EvidenceEvent`, `TokenEvent`, `DoneEvent`, `ErrorEvent`, `ToolStatus` |
| Prompts | `PromptTemplate`, `render`, `render_tool_index` |
| Synthesis | `synthesize` |
| Carry-over | `ContextStore`, `InMemoryContextStore`, `JsonBlob` |
| Config | `create_llm_provider`, `get_llm_config`, `load_config_document`, `resolve_role_config`, `role_model_env_var`, `llm_role_is_disabled`, `LLMConfigDocument` |
| Tracing | `install_file_tracing`, `FileTraceRecorder`, `LLMTraceConfig`, `serialize_record`, `interaction_scope`, `agent_run_scope` |
| Errors | `AgentKitError`, `LLMConfigError`, `LLMConfigNotFoundError`, `LLMConfigInvalidError`, `UnknownLLMRoleError` |

Tool types (`ToolDefinition`, `Message`, `Role`, `ToolCall`) and the loop itself
come from [`llm-core`](../llm-core/README.md).
