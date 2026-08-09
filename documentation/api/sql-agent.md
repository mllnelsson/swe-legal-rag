---
type: API Endpoint
title: SQL Agent Endpoint (POST /api/sql)
description: The POST /api/sql text-to-SQL contract — a Swedish question in, the generated read-only query and its rows out, never an interpreted answer — plus the caller's obligation to surface the query and the never-500s refusal semantics.
resource: POST /api/sql
tags: [api, sql, agent, text-to-sql, llm]
timestamp: 2026-08-09T00:00:00Z
---

# SQL Agent Endpoint (`POST /api/sql`)

A Swedish free-text question in; the SQL query the [SQL agent](/packages/agents.md) wrote
to answer it, and that query's rows, out. Complements [`POST /api/search`](/api/search.md),
which finds passages but cannot count or aggregate — "hur många överklaganden avslogs
2026?" has no answer in a search hit. Implemented by `agents.run_sql_agent`
(`packages/agents/`); this route (`packages/api/src/api/routes/sql.py`) is a thin
adapter over it.

## Request

```json
{
  "question": "string (1-2000 chars)"
}
```

422 on a question outside that length.

## Response

```json
{
  "answered": true,
  "sql": "string | null",
  "columns": ["string"],
  "rows": [["value"]],
  "row_count": 0,
  "truncated": false,
  "note": "string",
  "assumptions": ["string"],
  "attempts": [
    {"sql": "string", "ok": true, "error": "string | null", "row_count": "int | null"}
  ],
  "iterations": 0
}
```

`rows` values are already coerced to JSON primitives — a `date` or `UUID` column arrives
as a string, not something the caller has to decode.

**The last successful `run_sql` call is the answer.** `attempts` is the full trail, not
just the winner: every query the agent tried, in order, each marked `ok` and, if it ran,
its `row_count`. This is what lets a reader see that the agent grounded a predicate before
committing to the query that produced the answer, not just trust that it did.

## The consumer's obligation

**This agent never interprets what the rows mean, and the caller must not either without
showing the query.** A count reads as authoritative, and unlike a search hit it carries no
excerpt to check it against — a downstream conversational agent that turns `row_count: 12`
into "12 överklaganden avslogs" without also surfacing `sql` is asserting something it
cannot itself verify. Any caller of this endpoint, including a future agent that uses it as
a tool, is expected to display or otherwise expose `sql` alongside whatever it does with
`rows`.

## What the agent knows

The agent's knowledge of the corpus — table and column descriptions, which columns are
free-text, which can never be returned, and three worked example queries — comes from
the checked-in [`semantic_model.yaml`](/reference/semantic-model.md), rendered into the
`TEXT_TO_SQL` prompt's schema and examples blocks. Structural facts (types, nullability,
foreign keys) are read live from the ORM, so only the meaning of a column is
hand-maintained; a migration that adds a column without describing it fails the
[startup check](/reference/semantic-model.md#fatal-at-api-startup), not a silent gap in
the prompt.

## Grounding: why a query can be refused mid-run

Several columns hold free text rather than a controlled vocabulary (`documents.category`,
`documents.decision_outcome`, `entities.name` — see [the SQL agent
decision](/decisions/sql-agent.md) for why). A `run_sql` call whose **predicate** touches
one of these is refused until the agent has called `list_column_values` for that column
in the same run; grouping or selecting the column does not trigger the requirement, only
filtering on it does. The refusal is not visible to the caller as an error — it lands in
`attempts` as one more `ok: false` entry with the refusal message, and the agent's tool
loop uses it to correct the next query. A caller only sees this as a failed attempt in the
trail, or, if the model never recovers, as `answered: false`.

## Assumptions

With no user to disambiguate mid-conversation, the agent picks a reading on genuine
ambiguity (e.g. whether a bare year means `decision_date`, `case_number`, or
`decision_number` — the default is `decision_date`) and records it via `note_assumption`.
Every recorded choice surfaces in `assumptions`; an empty list means the question needed
no interpretive judgment call, not that none was possible.

## Never 500s

An unanswerable question — out of schema, an exhausted tool loop, or a query the model
never managed to ground — comes back `answered: false` with the reason in `note`, not an
HTTP error. `sql` is `null` and `rows`/`columns` are empty in that case. A caller has one
response shape to handle, not a success path and a separate error path.

## Settings

`SqlAgentSettings` (`agents/config.py`): `sql_agent_max_iterations` (8, the tool-loop
budget), `sql_agent_max_rows` (200, per `run_sql` call — a listing query that exceeds it
comes back `truncated: true` rather than silently clipped), `sql_agent_statement_timeout_ms`
(5000), `sql_agent_max_column_values` (100, distinct values `list_column_values` returns
per call).

## Observability

Traced with `source="agents.sql"`, `prompt="TEXT_TO_SQL"`. `llm_core.tool_loop` already
emits one trace record per iteration, so no additional wiring happens at this route — see
[LLM Observability](/observability.md).
