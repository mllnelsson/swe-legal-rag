---
type: Decision
title: Forced grounding for the text-to-SQL agent
description: Why the SQL agent's predicates over free-text columns must be grounded against real column values before a query runs, why that precondition is enforced in code rather than left to the prompt, the rejected structured-query-DTO alternative, and the safety posture — including why no dedicated read-only database role was added.
tags: [sql, agent, decision, safety, grounding]
timestamp: 2026-08-09T00:00:00Z
---

# Forced grounding for the text-to-SQL agent

**Status:** Accepted — implemented in [`packages/agents`](/packages/agents.md), served at
[`POST /api/sql`](/api/sql-agent.md).

## The problem: the corpus's metadata is not a controlled vocabulary

Verified against the live 185-document corpus. `documents.decision_outcome` reads like a
category but is free-text prose — the verbatim closing sentence of the decision. Over 40
distinct values exist, including `"Överklagandenämnden avslår överklagandet."` (76
occurrences) beside `"Överklagandenämnden avslår A:s begäran om att få höra ett vittne i
ärendet."`, which rejects a *witness request*, not the appeal — as well as compound
outcomes (`"1. ... avslår ... 2. ... avvisar ..."`) and at least one bare `"avslaget"`.
`documents.category` has the same problem at smaller scale: near-duplicate values sit side
by side (`Utlämnande av handling` / `Utlämnande av handlingar` / `Utlämnande av
ljudupptagning`, `Handlingsoffentlighet`), and the keyword entities extracted from the same
text split the same way.

A naive `WHERE decision_outcome ILIKE '%avslår%'` therefore miscounts in both directions —
it would catch the rejected witness request and, on a compound outcome, potentially miss
or double-count. The only way to filter these columns correctly is to look at what values
actually exist before writing the predicate.

## Decision: grounding is a precondition enforced in code, not requested in the prompt

The system prompt does ask the model to call `list_column_values` before filtering on a
free-text column. That request is not the control. `agents.sql._tools._run_sql` refuses to
execute any `run_sql` call whose **predicate** touches `documents.decision_outcome`,
`documents.category`, or `entities.name` — the columns flagged `free_text: true` in
[`semantic_model.yaml`](/reference/semantic-model.md), exposed as
`agents.sql._schema.grounding_required_columns()` — until `list_column_values` has been
called for that exact column earlier in the same run (`GroundingState.grounded_columns`).
The refusal is returned as an ordinary tool result, not raised as an error, so the
model's next iteration corrects itself through the loop's existing repair path — a
rejected query looks like any other tool failure to `tool_loop`, not a special case.

**Only filtering counts, not projecting or grouping.** `find_predicate_columns` scans only
predicate *segments* of a normalised copy of the statement — each running from a
`WHERE`/`HAVING`/`ON` to the next of `select | group by | order by | limit | offset |
fetch | window | union | intersect | except`. This matters because the agent's own
natural first move to explore a free-text column is
`SELECT category, count(*) FROM documents GROUP BY 1` — which *is* an act of grounding.
Demanding that query itself be pre-grounded would deadlock the loop: there would be no way
to satisfy the precondition for the query whose purpose is to satisfy it. See [the guard
fix](#the-guard-fix-a-join-no-longer-drags-group-by-into-the-predicate) below for why segments,
rather than "everything after the first `WHERE`", is the right scan.

This is what makes a mid-tier model (Mistral Medium, chosen because text-to-SQL syntax
itself is not the hard part of this task) defensible for an ungrounded, unsupervised
Swedish question: the model does not have to reliably *remember* to check a column's
values, because it is structurally prevented from filtering on one it has not checked.

## Rejected alternative: a structured query DTO

Considered: have the LLM emit a small structured object (`{filter, group_by, metric}`) and
compile it deterministically to SQL, extending `shared/dtos/search.py`'s `DocumentFilter`
rather than generating SQL text at all.

- **For:** zero injection surface, fully unit-testable, no static guard needed.
- **Against:** caps the system at whatever the DTO's shape can express, and open-ended
  aggregate questions are the entire point of this agent — a DTO expressive enough to
  answer them converges on reinventing SQL badly.

**Honest framing:** at 185 documents the entire metadata table fits comfortably inside a
model's context window, and arguably neither this agent nor the DTO alternative is
strictly necessary yet — a model could just be shown the rows. At the [PRD's target
~1000 documents](/prd.md) that stops being true. This agent is built for the corpus size
the system is meant to reach, not the one it happens to hold today; it is the flexible
choice, not the easy one, and that trade only pays off past the point a full table dump
stops fitting.

## Safety posture

Two independent controls:

1. **Postgres' own `READ ONLY` transaction** (`agents.sql._sandbox.execute_readonly`) is
   the actual guarantee. Every statement — the agent's and the tool executors' own
   `list_column_values` queries alike — runs inside `SET TRANSACTION READ ONLY` plus a
   `SET LOCAL statement_timeout`, and the transaction is always rolled back. This holds
   regardless of what the static guard fails to recognise.
2. **`agents.sql._guard.check_sql`** is defence in depth, not the primary control: single
   statement, must start `SELECT`/`WITH`, forbidden keywords including data-modifying CTEs
   (`WITH x AS (DELETE ... RETURNING ...)` is SELECT-headed but writes — the head-keyword
   check alone would miss it), `pg_*` identifiers blocked, no `SELECT *` (`count(*)`
   allowed), blocked columns rejected, and a table allow-list.

**The table allow-list is what keeps `sessions` (conversation history) and `tasks`
(pipeline bookkeeping) unreachable.** No dedicated, narrower database role was created for
this agent — it runs on the application's own connection, the same one every other API
request uses. The allow-list — `agents.sql._schema.exposed_tables()`, derived from the
`tables:` named in [`semantic_model.yaml`](/reference/semantic-model.md), with `sessions`,
`tasks`, and `alembic_version` refused outright by the loader regardless of what the file
says — enforced by the guard before a statement ever reaches Postgres, is therefore the
only thing standing between a generated query and those two tables; a bug in the guard's
table-reference scan is a real exposure in a way it would not be behind a Postgres role
scoped by grant. This is an accepted trade for now — see [deployment
state](/reference/deployment-state.md): nothing is deployed yet, so there is no operator
cost to revisiting it before this agent reaches a real environment, and doing so is a
re-evaluation trigger below.

## The startup check became fatal

The semantic model's ORM-agreement check (`agents.check_semantic_model()`) was originally
asserted only by a unit test. It is now the first thing `packages/api/src/api/main.py`'s
`_lifespan` does, before storage, tracing, or any provider — and it is fatal: a
disagreement between [`semantic_model.yaml`](/reference/semantic-model.md) and the ORM
refuses to let the API start.

This reverses an earlier stance, recorded at the time in the schema module's own
docstring, that refusing to start the API server over a schema-notes gap would be a
worse failure than serving a slightly thinner prompt. That reasoning held while the file
supplied only descriptive prose — a column reaching the model as a bare name was a
degraded prompt, not a broken guarantee. It stopped holding once the same file became
the source of the agent's table allow-list and its grounding policy: an undetected gap
there is not a thinner prompt, it is an allow-list or a grounding requirement that no
longer matches the database being queried, silently. There is no reduced mode worth
serving in that situation, so the check moved from "asserted by a test" to "checked, and
fatal, before the process accepts a request."

## The guard fix: a JOIN no longer drags GROUP BY into the predicate

`find_predicate_columns` originally scanned from the first `WHERE`/`HAVING`/`ON` to the
**end of the statement** as one predicate region. A `JOIN ... ON ... GROUP BY
entities.name` therefore demanded grounding for a column the query only groups by — the
exact deadlock this precondition exists to avoid (see above), reintroduced the moment a
query contained a `JOIN`. It now scans predicate *segments* instead, each closed by the
next of `select | group by | order by | limit | offset | fetch | window | union |
intersect | except`. `from` is deliberately **not** a terminator: treating it as one
would truncate `substring(decision_outcome FROM 1 FOR 5) = '...'` mid-expression and let
a filter through ungrounded. Covered by four regression tests in
`packages/agents/tests/unit/test_guard.py`.

## Consumer obligation

No code enforces this — it has to be stated and has to survive into anything that reuses
this agent. See [the endpoint's consumer-obligation section](/api/sql-agent.md#the-consumers-obligation)
for the full statement: the response carries the SQL and whoever consumes this agent, now
or as a tool inside a future conversational agent, is obliged to surface it alongside
whatever it does with the rows.

## Re-evaluation triggers

Revisit if:

- The corpus approaches a size where a full metadata dump no longer fits a context window
  comfortably — the honest framing above stops being generous.
- This agent, or anything built on top of it, is exposed outside the application's own
  trusted callers — the table allow-list is not a substitute for a scoped database role
  once that is true.
- A new free-text column is added to an exposed table and should require grounding —
  `check_semantic_model()` catches a column with no `semantic_model.yaml` entry at all,
  but nothing catches a described column whose `free_text: true` flag should have been
  set and was not; that judgment call stays manual. See [how to add a
  column](/reference/semantic-model.md#how-to-add-a-column).
