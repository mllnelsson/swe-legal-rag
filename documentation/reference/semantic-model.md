---
type: Reference
title: semantic_model.yaml — The SQL Agent's Semantic Model
description: The checked-in file format for what the SQL agent is told about the corpus — column notes, free-text/selectable flags, worked examples — the two-way ORM check that keeps it honest, the fatal startup check, and how to add a column.
resource: semantic_model.yaml
tags: [sql, agent, schema, yaml, config, grounding]
timestamp: 2026-08-09T00:00:00Z
---

# semantic_model.yaml — The SQL Agent's Semantic Model

`semantic_model.yaml`, at the repo root, is the single source of truth for what the
[SQL agent](/packages/agents.md) is told about the database it queries: which tables
and columns exist, what each column *means*, which hold free-text prose that must be
grounded before a predicate touches them, which can never be returned, and three
worked example queries. It replaces a hand-written block of Python dicts and
frozensets that used to live inside `agents/sql/_schema.py` — that module is now
purely a renderer over this file, described below.

Loaded and validated by
[`agents.sql._semantic_model`](/packages/agents.md#the-semantic-model-agentssql_semantic_modelpy);
this page documents the file contract. The loader deliberately mirrors
[`ai.llm_config`](/reference/llm-config.md) — same walk-up-from-cwd discovery, same
`extra="forbid"` pydantic models, same `@lru_cache`d process-wide getter — because that
is this project's established pattern for a checked-in YAML document that a startup
check must agree with reality.

## What belongs here, and what does not

**Structural facts never belong in this file.** Column type, nullability, and foreign
keys are read live from `shared.models.Base.metadata` when the prompt is rendered, so
they cannot drift from a migration. Only the half a machine cannot derive is written
here: what a column *means*, and the three flags below.

## File format

```yaml
version: 1

tables:
  documents:
    description: >
      Ett beslut från Överklagandenämnden per rad. Detta är korpusens navtabell.
    columns:
      id: Primärnyckel.                     # a bare string is the note
      raw_text:
        note: Hela beslutets text.
        selectable: false
      decision_outcome:
        note: >
          Den ordagranna slutklämmen ur beslutet, inte en kategori. ...
        free_text: true

examples:
  - question: Hur många överklaganden om utlämnande av handling avslogs 2026?
    grounding:
      - [documents, decision_outcome]
      - [documents, category]
    sql: |
      SELECT count(*) AS antal
      FROM documents
      WHERE decision_outcome ILIKE '%avslår överklagandet%'
        AND category IN ('Utlämnande av handling', 'Utlämnande av handlingar')
        AND extract(year FROM decision_date) = 2026
    note: >
      Båda fritextkolumnerna lästes med list_column_values först. ...
```

| Section | Purpose |
|---|---|
| `version` | Must equal `1` — the only version this build understands. |
| `tables` | One entry per exposed table: a `description` and a `columns` mapping. **Every table exposed to the agent must be named here — omission is how a table stays unreachable.** |
| `tables.<name>.columns` | One entry per column on that table. A **bare string** is shorthand for `{note: <string>}` — most columns need nothing else. A **mapping** adds `note` plus zero or more flags. |
| `examples` | Worked queries shown to the agent: `question`, `grounding` (the `[table, column]` pairs the query filters on), `sql`, `note`. |

### Column flags

| Flag | Default | Meaning |
|---|---|---|
| `free_text: true` | `false` | Prose, not a controlled vocabulary. A predicate over this column is refused by `run_sql` until its actual values have been read with `list_column_values` in the same run — see [the grounding decision](/decisions/sql-agent.md). |
| `selectable: false` | `true` | May never appear in a result — an embedding vector, a `tsv` lexeme index, a whole document's raw text. Stays listed in the rendered schema, marked, rather than silently vanishing and inviting the model to guess it exists. |

### The words the file must never contain

`FRITEXT` and `[EJ VALBAR]` are the markers the rendered prompt uses for `free_text`
and `selectable: false` respectively. **Never type either string into a `note`.** Both
are rendered from the flag by `agents.sql._schema`, so a note that also spells the
marker out by hand is one fact written twice — and the two can disagree, which is
exactly the defect this file replaced (a column described as `FRITEXT` in prose while
absent from the old code's grounding set, or vice versa).

## The never-exposed floor

`sessions` (conversation history) and `tasks` (pipeline bookkeeping) — plus
`alembic_version` — can never be named under `tables:`, even by mistake.
`agents.sql._semantic_model._NEVER_EXPOSED` is a hard-coded set enforced *against* the
file at load time: naming one of them there is a validation failure, not something the
file could quietly grant. This exists because the table allow-list itself now comes
from data (`tables:`'s keys) rather than a constant in source — a bad YAML edit is a
more plausible failure mode than a bad code edit, and this floor is what stops such an
edit from reaching chat history or task bookkeeping.

## The two-way ORM check

`check_semantic_model()` proves the file and `shared.models.Base.metadata` describe the
same database, in **both directions**, reporting every disagreement at once rather than
the first:

- a table named under `tables:` that no longer exists in the ORM
- a column that exists on an exposed table but has no entry under `columns:`
- a column named under `columns:` that no longer exists

It also holds every entry under `examples:` to the rules the agent itself is held to:
each example's `sql` must pass `agents.sql._guard.check_sql()`, and must declare under
`grounding` every free-text column it filters on — the same precondition `run_sql`
enforces live. An example that skipped this would be teaching the model to write a
query the tools would themselves refuse to run.

## Fatal at API startup

`agents.check_semantic_model()` is the **first** thing `packages/api/src/api/main.py`'s
`_lifespan` does — before storage, tracing, or any provider construction. A disagreement
between the file and the ORM refuses to serve at all, and the same call warms the
`@lru_cache`d `get_semantic_model()` so no request pays the file read.

This is a **fatal** check by design, not a warning. The file supplies the agent's table
allow-list and its grounding policy, not merely descriptive prose, so there is no
reduced mode worth serving — a column reaching the agent as a bare, undescribed name
means the allow-list and the grounding policy have already silently drifted from what
the ORM actually holds. See [the fatal-at-startup
reversal](/decisions/sql-agent.md#the-startup-check-became-fatal) for why this is a
change from how the equivalent check used to be treated.

## The dev script

```bash
uv run python scripts/check_semantic_model.py           # exit 0, or 1 with the reason on stderr
uv run python scripts/check_semantic_model.py --print    # also dump the rendered schema and examples text
```

The same check the API runs at startup, available without booting the API. `--print`
dumps the exact schema and examples block the model is given — previously the only way
to see that text was to read a trace record after a billed call; now it costs nothing
and needs no network. **Run it after any migration** that touches an exposed table —
see [local dev](/playbooks/local-dev.md#migrations-both-platforms).

The Docker image copies `semantic_model.yaml` into the container next to
`llm_config.yaml` (`Dockerfile`), so the same file the API validates at startup is what
ships.

## How to add a column

1. Run the migration.
2. `uv run python scripts/check_semantic_model.py` — it now fails, naming the
   undescribed column.
3. Add an entry under the right table's `columns:` in `semantic_model.yaml`: a bare
   string if the column needs only a sentence, or a mapping with `note` plus `free_text`
   and/or `selectable` if it needs a flag.
4. If the column holds prose rather than a controlled vocabulary, set `free_text: true`
   — nothing else enforces this judgment call; `check_semantic_model()` only confirms
   every column has *a* description, not that its flags are the right ones.
5. Re-run the script. If it still fails on an example, that example now filters on a
   newly-flagged free-text column without declaring it under `grounding` — fix the
   example, not the check.

## How to add a table

Same shape, one level up: add a `tables.<name>` entry with a `description` and every
column. A table left out of `tables:` stays unreachable regardless of what exists in
the ORM — there is no separate allow-list to update.

## Citations

See [the SQL agent decision](/decisions/sql-agent.md) for why grounding is enforced
this way at all, and [`packages/agents.md`](/packages/agents.md) for how the loaded
document flows into the schema/guard/tools modules.
