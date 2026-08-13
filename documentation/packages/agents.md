---
type: Package
title: agents Package
description: The LLM-tool-loop agents that answer questions the deterministic retrieval API cannot — the text-to-SQL agent behind POST /api/sql and the conversational agent behind POST /api/chat — their module layout, and the injected-toolset seam that keeps the dependency running api to agents.
resource: packages/agents
tags: [package, agents, sql, chat, tool-loop, llm]
timestamp: 2026-08-13T00:00:00Z
---

# agents Package (`packages/agents/`)

An **agent** here means an LLM driving a tool loop toward an answer, as opposed to the
deterministic retrieval tool set in [api](/packages/api.md). Each is a function over its
inputs rather than a service that reaches into a database itself, which is what lets one
be called as a tool by another. Depends on `shared` (models, for the live schema) and
`ai` + `llm-core` (the prompt templates and the tool loop); depended on by `api`.

Two live here, and they differ in shape:

| Agent | Endpoint | Shape |
|---|---|---|
| [`run_sql_agent`](/api/sql-agent.md) | `POST /api/sql` | Stateless and one-shot — a question in, a query and its rows out |
| [`run_chat_agent`](/retrieval/chat-agent.md) | `POST /api/chat` | Streams, and is driven from a conversation |

The conversational agent breaks the "no sessions, no streaming" rule the SQL agent
established, but not the one that matters: it still takes no database of its own. Its
tools arrive as an injected `ChatToolset`, and it calls `run_sql_agent` as one of them.

## Module layout

| Module | Role |
|---|---|
| `__init__.py` | Public surface: `run_sql_agent`, `SqlAgentRequest`, `SqlAgentResult`, `SqlAttempt`, `SqlRows`, `SqlAgentSettings`, `check_semantic_model`, `build_schema_description`, `build_examples_block`, `find_semantic_model_path`, `load_semantic_model`, and the package's errors |
| `errors.py` | `AgentError` base; `SqlRejectedError` (the guard's refusal, fed back to the model as a tool result, not raised to the caller); `SemanticModelNotFoundError`, `SemanticModelInvalidError`, `SemanticModelIncompleteError` (the three semantic-model failure modes, mirroring the `LLMConfig*` trio in `ai.llm_config`) |
| `config.py` | `SqlAgentSettings` and `ChatAgentSettings` (`BaseSettings`) with their `@lru_cache` getters — see [the SQL endpoint's settings](/api/sql-agent.md#settings) and [the chat agent's](/retrieval/chat-agent.md#settings). Loop bounds live here rather than in [`llm_config.yaml`](/reference/llm-config.md), which assigns models, not budgets |
| `sql/_dtos.py` | The wire contract as plain Pydantic models — `SqlAgentRequest`, `SqlAgentResult`, `SqlAttempt`, `SqlRows` — deliberately free of FastAPI types, the same way `api.services.search_service.SearchQuery` is, so the same models serve an HTTP route, a test, or a future MCP tool wrapper |
| `sql/_semantic_model.py` | Loads and validates [`semantic_model.yaml`](/reference/semantic-model.md): `find_semantic_model_path()`, `load_semantic_model()`, `@lru_cache`d `get_semantic_model()`, `resolve(document)`, and `check_semantic_model()` — the two-way check against `shared.models.Base.metadata` |
| `sql/_schema.py` | A pure renderer over the loaded document, no longer a source of prose itself. `exposed_tables()`, `blocked_columns()`, `grounding_required_columns()`, `exposed_column_names()`, `build_schema_description()`, `build_examples_block()` — each takes an optional `document` and falls back to the process-wide one |
| `sql/_guard.py` | `check_sql(sql, document=None)` — static checks on model-authored SQL before it reaches Postgres; `find_predicate_columns(sql, document=None)` — which free-text columns a query's predicate touches, as opposed to merely projecting or grouping by |
| `sql/_sandbox.py` | `execute_readonly()` — runs a statement inside `SET TRANSACTION READ ONLY` plus a `SET LOCAL statement_timeout`, always rolled back regardless of outcome |
| `sql/_tools.py` | The three tools the loop is given (`list_column_values`, `run_sql`, `note_assumption`) and `GroundingState`, the mutable per-run record of what the agent has grounded, assumed, and attempted. `build_sql_tools(session, settings, document=None)` |
| `sql/_agent.py` | `run_sql_agent(..., document=None)` — wires the prompt, the tools, and `llm_core.tool_loop` together, and assembles the result from the trail `GroundingState` left behind |
| `chat/_dtos.py` | The chat wire contract: `ChatAgentRequest`, the `AgentEvent` union, `SourceReference`, the `ChatTool` / `ProgressLabel` / `ToolStatus` enums, and the shapes a toolset returns (`SearchOutcome`, `Vocabulary`, `DecisionText`, `DecisionProfile`) |
| `chat/_protocols.py` | The `ChatToolset` Protocol — five async capabilities in the agent's own shapes. See [the seam](#the-toolset-seam) below |
| `chat/_tools.py` | `build_chat_tools(toolset, settings, reader_provider=None)` → the six tool definitions, their executors and `ChatState`; plus `label_for_call()` and `FREE_TEXT_FILTER_FIELDS`, the grounding precondition's column list |
| `chat/_reader.py` | `read_decision_text()` — the one-shot sub-agent a whole decision goes to, and `format_decision_text()`, which marks each appendix boundary before it does |
| `chat/_agent.py` | `run_chat_agent(request, toolset, ...)` — runs the loop as a task pushing to a queue the generator drains, then streams one synthesis call over the evidence the agent selected |

Both agents open their correlation scope the same way, and neither mints an
`interaction_id` outright: `ai.interaction_scope()` **inherits** one already in the
trace context and mints only when there is none. That is what lets `run_sql_agent`,
reached as the conversational agent's `query_corpus` tool, keep its spend inside the
turn that asked for it, while the same function reached from `POST /api/sql` — with no
caller to inherit from — still opens an interaction of its own. Each also opens an
`ai.agent_run_scope()`, which always mints, so two `query_corpus` calls in one turn stay
distinguishable. See [LLM Observability](/observability.md).

Every function above the `_semantic_model.py` layer takes an optional `document`
parameter and falls back to the cached, process-wide one — this is what lets a test
exercise the guard, the tools, or the whole agent against an alternative
`SemanticModelDocument` without touching the module-level cache.

## The toolset seam

`api` already depends on `agents`, for `run_sql_agent`. The conversational agent needs
the retrieval services that live in `api`, so importing them back would close a cycle.

`ChatToolset` is the seam instead. `agents` declares the five capabilities it needs, in
its own shapes; `api` supplies an object that satisfies them
(`api/services/chat_toolset.py`). Nothing in `agents` imports `api`.

| Capability | What `api` maps it onto |
|---|---|
| `search` | `search_service.search_documents` |
| `vocabulary` | `search_service.get_filters`, plus keyword/concept name lookup |
| `decision_text` | `document_service.get_document_chunks` |
| `decision_profile` | `document_service.get_document_detail` |
| `tabular_query` | `agents.run_sql_agent` |

The second benefit is testing: a scripted toolset is a plain object with five methods,
so the whole loop is exercised with no database, no HTTP and no model. See
[testing strategy](/testing.md).

## The semantic model (`agents/sql/_semantic_model.py`)

What the agent is told about the database comes from two sources that must agree.
Structural facts — column type, nullability, foreign keys — are read live from
`shared.models.Base.metadata`, so they cannot drift from a migration. Everything a
machine cannot derive — what a column *means*, which hold free-text prose, which can
never be returned, which tables exist at all, and three worked example queries — is
hand-maintained in the checked-in [`semantic_model.yaml`](/reference/semantic-model.md).

`check_semantic_model()` is what keeps the two in step: it checks both directions (a
described table/column that no longer exists, and an existing column nobody described)
and also re-checks every example against the same guard and grounding rules the live
agent is held to. It is **fatal at API startup** — see [the startup-check
reversal](/decisions/sql-agent.md#the-startup-check-became-fatal) — and is also what
[`scripts/check_semantic_model.py`](/reference/semantic-model.md#the-dev-script) runs.
The table allow-list (`sql/_schema.exposed_tables()`) is therefore data-driven from
`tables:` in the YAML rather than a Python constant, with `sessions`, `tasks`, and
`alembic_version` refused outright by the loader — `_NEVER_EXPOSED` — even if a bad
edit named one.

## The schema prompt

`build_schema_description()` renders the loaded document plus live SQLAlchemy metadata
into the schema block the model reads; `build_examples_block()` renders the three
worked queries into a second block, placed between the schema and the question in the
`TEXT_TO_SQL` user template. `blocked_columns()` (`embedding`, `tsv`, `raw_text`) stay
listed in the schema but marked `[EJ VALBAR]` so the model knows why it cannot have
them, rather than silently vanishing and inviting a guess. `grounding_required_columns()`
names the free-text columns a predicate must be grounded against — see [the SQL agent
decision](/decisions/sql-agent.md) for why. Both markers are rendered from the YAML's
`selectable`/`free_text` flags, never typed into a note by hand — see [the file
format](/reference/semantic-model.md#the-words-the-file-must-never-contain). The notes
are written in Swedish, matching the prompt they land in.

## Safety layers

Two independent controls, not one:

1. **The read-only transaction** (`_sandbox.execute_readonly`) is the actual guarantee —
   Postgres refuses a write regardless of what the static guard missed.
2. **The static guard** (`_guard.check_sql`) is defence in depth: single statement only,
   must start `SELECT`/`WITH`, no data-modifying keywords (including inside a CTE), no
   `pg_*` identifiers, no `SELECT *` (`count(*)` is fine), no blocked columns, and only the
   exposed tables reachable. Every check runs against a normalised copy of the statement
   with comments and string literals stripped, so a keyword sitting inside a literal (e.g.
   `WHERE category ILIKE '%create%'`) cannot trip a rule; `extract(year FROM
   decision_date)` and similar keyword-argument calls are specially blanked before the
   table-reference scan so their `FROM` is not read as a table name.

Both are covered in full in [the SQL agent decision](/decisions/sql-agent.md), including why
there is no dedicated read-only database role.

## Tests

`packages/agents/tests/unit/test_semantic_model.py` covers the loader and
`check_semantic_model()`: both directions of ORM drift, the `_NEVER_EXPOSED` floor, the
bare-string/mapping column shorthand, and that a rejected or ungrounded example fails
the check. `test_schema.py` and `test_guard.py` (the latter with regression coverage
for the predicate-segment fix — see [the SQL agent
decision](/decisions/sql-agent.md#the-guard-fix-a-join-no-longer-drags-group-by-into-the-predicate))
cover the renderer and the static guard against the shipped document.
`scripts/tests/unit/test_check_semantic_model.py` covers the dev script's exit codes
and `--print` output. `test_agent.py`/`test_tools.py` cover the tool executors and the
loop against a scripted `LLMProvider` (no live model call).
`packages/agents/tests/integration/test_sandbox_integration.py` is the one thing only a
real Postgres can prove: that a write is refused by the transaction itself, not just by the
static guard, and that a failed statement leaves the session usable for the request that
follows. See [testing strategy](/testing.md).

`test_chat_agent.py` covers the conversational loop the same way — a scripted
`LLMProvider` and a fake `ChatToolset`, no database and no model. What it pins is
mostly the behaviour that would be expensive to discover in production: that an
ungrounded filter is refused and the loop recovers from the refusal, that a keyword
filter is not, that the terminal `answer` tool ends the run, that `event: sql` precedes
the answer, that a cited appendix keeps its label, and that **no whole decision text
ever reaches an orchestrator message** — the invariant the reading sub-agent exists to
maintain.

`TestCorrelation`, in both `test_agent.py` and `test_chat_agent.py`, installs a
recording `TraceRecorder` and pins the correlation contract against the real agent
functions rather than a stub: that a nested run inherits its caller's `interaction_id`,
that a standalone run mints one, that each invocation gets its own `agent_run_id`, and
that orchestration records name their prompt. Costing a question is a sum over one key,
so a test that lets two ids into one turn is the one that lets the cost figure be wrong.

Running either agent over many real questions at once, against a real provider and
outside pytest, is what
[`scripts/run_agent.py`](/playbooks/live-testing.md#option-d-llm-task-runner-scriptsrun_agentpy)
is for.
