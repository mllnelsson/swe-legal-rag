---
type: Playbook
title: Extracting agent-kit + llm-core into a standalone repo
description: How to lift the domain-free agent-kit and llm-core packages out of this monorepo into a single standalone git package (llm-core nested under agent-kit) and consume it back as a pinned git dependency — no PyPI, no hand-built wheels.
tags: [agent-kit, llm-core, packaging, uv, extraction, workflow]
timestamp: 2026-08-31T00:00:00Z
---

# Extracting agent-kit + llm-core into a standalone repo

`llm-core` (provider abstraction, tool loop, scratchpad) and `agent-kit`
(plan→execute→synthesize orchestration, config loader, tracing) were built domain-free so they
can be lifted out of this monorepo and reused as a standalone agent library. This playbook is
the extraction: move both into **one** new git package — `llm_core` **nested inside**
`agent_kit` — then consume it back here as a **pinned git dependency**. No PyPI, no
hand-carried wheels.

`llm_config.yaml` and the `LLM_*` environment variables **stay in this repo**; agent-kit keeps
owning their schema, env aliases and defaults. See [LLM packages](/packages/llm-core.md) and
[agent-kit](/packages/agent-kit.md) for what each package contains.

## Why this is safe

- **No blockers.** `agent-kit` and `llm-core` import nothing from `shared`/`ai`/`agents`/
  `api`/`worker-*`. The boundary is already clean — the two packages don't change; only their
  *home* and this repo's *imports* do.
- **Both are `uv_build` distributions**, `version = "0.1.0"`, ship `py.typed`. `agent-kit`
  already depends on `llm-core`; nesting turns that dependency into an internal subpackage.

## Do you need to build a wheel? No.

A **pinned git source** is enough. `uv` builds the package in an isolated env at lock time and
freezes the exact commit in `uv.lock`; the *version is the git tag*. Reproducing on another
machine is `uv sync` — it only needs to reach the repo (GitHub over SSH, or a bare clone on a
file share). `uv build` wheels buy nothing here except a true airgap, and even then a bare git
repo on the share is simpler than version-matching `.whl` filenames. Skip wheels.

## The nesting, and its one cost

One distribution named `agent-kit`. `llm_core` moves **under** it as an internal subpackage
(`agent_kit._llm`), and `agent_kit/__init__.py` re-exports the public surface so callers write
`from agent_kit import Scratchpad, ProviderKind, …`. There is no separate `llm-core`
distribution any more — one package, one version, one dependency line here.

**The cost, stated plainly (and it is smaller than it first looks):** an AST scan of this repo
— *excluding the two packages themselves*, which are leaving — shows the migration is confined
to the **`llm_core` namespace**. This repo imports **26 symbols from top-level `llm_core`** and
exactly **one private module** (`llm_core._tracing`, whose two symbols are already exported at
`llm_core` top level — a redundant import, not a real reach-in). Everything else it uses from
the core is already under the **`agent_kit`** namespace (top-level plus the public subpackages
`config`, `errors`, `orchestrator`, `prompts`, `tracing`), and **nesting does not touch those**
— `agent_kit.*` keeps its name.

So the change here is: **repoint `from llm_core import …` → `from agent_kit import …`** (resolved
by the re-exports) and delete the one redundant `_tracing` import. No private-module churn worth
the name. The earlier worry about `llm_core._types` / `_config` / `providers._openai_compatible`
etc. was real *inside* the packages — those are agent-kit's own internals and move with it — but
this repo does not import them.

This migration is a code change in *this* repo. It is **not** part of standing up the new repo
and is not done in this guide — it's step C below, a follow-up you (or another agent) run once
the package exists. The exact symbol list is in [Import inventory](#import-inventory) so the
package's public surface can be designed to cover it.

> **Alternative if you'd rather not touch imports here:** keep `llm_core` as a second top-level
> package co-located in the new repo (a two-member `uv` workspace, or one distribution exposing
> both modules). Then this repo changes only dependency wiring and edits zero `.py` files. It is
> the lower-churn option, but it is not "one nested package" — noted only so the trade is on the
> record. The rest of this guide assumes the nested target you asked for.

## Import inventory

What this repo actually pulls from the core, so the new package's **public surface can be
designed to cover it** and another pass can tidy the import sites. Produced by AST scan of
`packages/**` and `scripts/**`, excluding `packages/agent-kit` and `packages/llm-core`. 35
files import the core across `ai`, `agents`, `api`, `worker-chunk`, `worker-extract`,
`worker-metadata`, `scripts`.

### Must be re-exported from `agent_kit` — the 26 `llm_core` top-level symbols

These are every `from llm_core import …` name in this repo. After nesting they must all resolve
via `from agent_kit import …`, so agent-kit's `__init__` must re-export each:

```
LLMCallRecord, LLMDisabledError, LLMOperation, LLMProvider, LLMResponse,
MaxIterationsError, Message, ProviderKind, Role, Scratchpad, StreamChunk,
ToolCall, ToolDefinition, ToolExecutionError, Usage,
aclose_async_openai, current_trace_context, generate, generate_structured,
get_async_openai, get_trace_recorder, run_tool_loop, set_trace_recorder,
trace_context, trace_outcome, traced_call
```

### The one private import to unify

`from llm_core._tracing import LLMCallRecord, set_trace_recorder` — **both are already exported
at `llm_core` top level** (and appear in the list above). This is a non-canonical duplicate:
repoint it to `from agent_kit import LLMCallRecord, set_trace_recorder` and the private path is
gone. It is the only underscore-module import of the core anywhere in this repo.

### Unchanged by nesting — the `agent_kit` namespace this repo already uses

Nesting keeps `agent_kit.*` names, so these need **no** change. Listed so the cleanup pass can
decide whether any deserve promotion to top-level re-exports (several read like they should be
`from agent_kit import …` rather than reaching into a subpackage):

| Import path | Symbols used here |
| --- | --- |
| `agent_kit` (top level) | `AgentRequest, ContextStore, ExecutionPhase, InMemoryContextStore, JsonBlob, PlanPhase, ScratchpadCodec, run_agent, synthesize` |
| `agent_kit.config` | `CONFIG_FILENAME, CONFIG_PATH_ENV, LLMConfigDocument, ProviderSpec, RoleDefaults, RoleSpec, SUPPORTED_VERSION, api_key_for, create_llm_provider, find_config_path, get_llm_config, llm_role_is_disabled, load_config_document, resolve_role_config, role_model_env_var, without_env_overrides` |
| `agent_kit.errors` | `LLMConfigError, LLMConfigInvalidError, LLMConfigNotFoundError, UnknownLLMRoleError` |
| `agent_kit.orchestrator` | `DoneEvent, ErrorEvent, EvidenceEvent, PlanReplyEvent, TokenEvent, ToolCallEvent, ToolResultEvent, ToolStatus` |
| `agent_kit.prompts` | `PromptTemplate, render, render_tool_index` |
| `agent_kit.tracing` | `FileTraceRecorder, LLMTraceConfig, TRACE_SCHEMA_VERSION, agent_run_scope, install_file_tracing, interaction_scope, relative_path_for, serialize_record` |

> Cleanup hints for the other agent: (1) guarantee the 26-symbol re-export set above, ideally
> with a `__all__` and a test that imports every name; (2) collapse the `_tracing` duplicate;
> (3) consider whether the `config`/`errors`/`orchestrator`/`prompts`/`tracing` subpackage
> imports should also be surfaced at `agent_kit` top level for a flatter public API, or left as
> subpackages by design — the layering is fine either way, this is an ergonomics call.

## Target shape

One new git repo, one package, `llm_core` nested inside:

```
agent-kit/                      # new git repo (git@github.com:mllnelsson/agent-kit.git)
  pyproject.toml                # [project] name = "agent-kit"; no workspace needed
  uv.lock
  src/
    agent_kit/
      __init__.py               # re-exports the llm_core public surface (from ._llm import …)
      _llm/                      # was packages/llm-core/src/llm_core/, moved in verbatim
      config/ orchestrator/ …    # unchanged
  tests/
  README.md  AGENTS.md  docs/
```

This repo then declares **one** git source (no `subdirectory`, no separate `llm-core` dep).

## Steps

### A. Stand up the new repo (single package, nested)

1. `uv init --lib agent-kit` in a sibling directory. This gives a single-package layout
   (`src/agent_kit/`, one `pyproject.toml` at the root) — no workspace. Copy `.python-version`
   (3.12).
2. Move `packages/agent-kit/src/agent_kit/*` into the new `src/agent_kit/`, and move
   `packages/llm-core/src/llm_core/` in **under** it as `src/agent_kit/_llm/`.
3. In the new repo, repoint agent-kit's *internal* imports: `from llm_core…` →
   `from agent_kit._llm…`. Then curate `src/agent_kit/__init__.py` to re-export the public
   surface that was `llm_core`'s (provider types, `Message`/`Role`/`ToolDefinition`,
   `LLMConfig`/`ProviderKind`, `Scratchpad`/`Handle`, tracing entry points, exceptions). Merge
   the two `dependencies` lists into the one `pyproject.toml`; drop the now-internal
   `llm-core` dependency and its `[tool.uv.sources]`.
4. Move both packages' `tests/` into the new repo's `tests/` and fix their imports the same
   way. Add `[tool.pytest.ini_options] asyncio_mode = "auto"`. `uv sync` then `uv run pytest`
   — green proves the nesting is sound and the boundary is genuinely clean.
5. Commit, push to `git@github.com:mllnelsson/agent-kit.git`, then
   `git tag v0.1.0 && git push --tags`.
   - **Other machine / file share:** clone over SSH, or push a bare clone
     (`git clone --bare`) onto the share and point the source at that path. No build step.

### B. Rewire this repo's dependency wiring

1. **Remove** `packages/agent-kit/` and `packages/llm-core/`.
2. **Root `pyproject.toml`:**
   - `[tool.uv.workspace] members` — no change if `["packages/*"]` (the dirs are just gone).
   - `[dependency-groups] dev` — remove the `"agent-kit"` and `"llm-core"` entries; add back
     `"agent-kit"` only (it now resolves via the git source).
   - `[tool.uv.sources]` — replace both workspace entries with a single git source:
     ```toml
     agent-kit = { git = "git@github.com:mllnelsson/agent-kit.git", tag = "v0.1.0" }
     ```
   - `[tool.pytest.ini_options] testpaths` — remove the `"packages/llm-core/tests"` and
     `"packages/agent-kit/tests"` lines.
   - `[tool.ruff] src = ["packages/*/src"]` — leave as-is (the dirs are simply absent).
3. **Per-consumer `pyproject.toml`.** In `ai`, `agents`, `api`: drop the `"llm-core"`
   dependency (keep `"agent-kit"`), and delete their own `[tool.uv.sources]` `llm-core`/
   `agent-kit` `{ workspace = true }` lines so they inherit the root git source. In
   `worker-chunk`, `worker-extract`, `worker-metadata`: add `"agent-kit"` to
   `[project].dependencies` (they import the core but declare nothing today).

### C. Migrate this repo's imports (the one code change)

Do this together with step B or right after — the two must land in the same commit, since
removing `llm-core` breaks every `from llm_core…` until it's repointed.

- `from llm_core import …` → `from agent_kit import …` — the 26 symbols in the
  [Import inventory](#import-inventory), resolved by the re-exports. This is the whole job.
- Collapse the single `from llm_core._tracing import LLMCallRecord, set_trace_recorder` into
  the `from agent_kit import …` line — both symbols are already public.
- `from agent_kit…` sites are unaffected — that namespace keeps its name, subpackages included.
- If any of the 26 turns out not to be re-exported, add it to agent-kit's `__init__` in the new
  repo rather than reaching into `agent_kit._llm…` from here.
- `uv lock` then `uv sync`. Confirm `uv.lock` pins `agent-kit` to the git commit behind
  `v0.1.0`, not a workspace path.

### D. Config & env — what stays, what agent-kit owns

- **Stays in this repo:** `llm_config.yaml` (root) and the `LLM_*` values in `.env`
  (provider keys, `LLM_MODEL_*` overrides, `LLM_TRACE_*`, optional `LLM_CONFIG_PATH`). These
  are deployment values for this project. See [LLM config](/reference/llm-config.md).
- **agent-kit owns the mechanism, and it travels with the package:** the schema
  (`agent_kit/config/_document.py`), the loader with cwd walk-up and `LLM_CONFIG_PATH`
  (`agent_kit/config/_loader.py`), and the env aliases/defaults (now under `agent_kit._llm`).
- **Known gap, deferred to the agent-kit repo:** `find_config_path()` currently *raises*
  `LLMConfigNotFoundError` when no `llm_config.yaml` is found. Shipping a reasonable built-in
  default document (and alerting on genuinely required env) is agent-kit-repo work, not part of
  this move.

### E. Documentation to bring over

The current per-package `README.md` files (`packages/agent-kit/README.md`,
`packages/llm-core/README.md`) fold into the new repo's single `README.md` + `docs/`. Beyond
those, the bundle here holds concept docs that are *about the generic core* and belong in the
new repo, docs that are pure domain and stay, and a few mixed ones to cherry-pick.

| From this bundle | Action | Why |
| --- | --- | --- |
| `packages/llm-core.md` | **bring** | Provider abstraction, tool loop, scratchpad — all generic (now the `agent_kit._llm` layer). |
| `packages/agent-kit.md` | **bring** | Orchestrator, config loader, tracing, context store — all generic. |
| `reference/llm-config.md` | **bring, trim** | Config document + env-var registry + precedence are agent-kit's. Drop the `embedding:` sections — embedding is a host concern the document only passes through. |
| `observability.md` | **bring, trim** | The tracing mechanism (`install_file_tracing`, `trace_context`, the wiring invariant, record schema, recorder lifecycle) is agent-kit's. Drop the domain examples. |
| `packages/agents.md`, `packages/ai.md`, `packages/api.md`, `packages/overview.md`, `retrieval/*`, `api/*`, `data-model/*`, `pipeline/*`, `frontend/*`, `reference/crawl-source.md` | **leave** | These describe *this project's use* of the library, not the library. |
| `decisions/architectural-register.md`, `decisions/llm-model-selection.md`, `testing.md` | **cherry-pick** | Copy only the entries/sections about the agent core (tool-loop shape, scratchpad, provider selection, testing a domain-free core). |

Moving these is not a straight copy — the two package docs now describe **one** package and
double up on Scratchpad and Tracing, so they merge. Section G is the exact procedure.

### F. Docs format in the new repo — agent-friendly, not OKF

The new package is a solo library; it does not need OKF's conformance machinery (required
`type` frontmatter, reserved `index.md`/`log.md`, per-week logs, `timestamp` discipline). Keep
the properties that make docs good for a coding agent to retrieve, drop the ceremony:

```
agent-kit/
  README.md            # what it is, install (the git-dep snippet), 30-second quickstart, a map of the rest
  AGENTS.md            # the agent's entry point — read-me-first for any assistant working in the repo
  docs/                # plain markdown concept files, no frontmatter, one concept each
    orchestrator.md    # run_agent, the plan→execute→synthesize phases
    tool-loop.md       # run_tool_loop and the board hook
    providers.md       # provider abstraction, the openai/gemini/null kinds
    scratchpad.md      # MERGED: the primitive + cross-turn persistence (see G)
    context-store.md   # ContextStore protocol, in-memory + how a host persists
    config.md          # MERGED: config document + env registry (see G)
    observability.md   # MERGED: the trace hook + recorder + wiring invariant (see G)
    README.md          # a hand-listed map of docs/ — no generated index, no log
  src/agent_kit/…
  tests/…
```

- **`AGENTS.md`** is the agent-friendly move — the emerging cross-tool convention (what
  `CLAUDE.md` is here, but tool-agnostic). Put the invariants an assistant must not violate:
  the layering rule (`agent_kit` orchestration on top of the nested `_llm` core, never the
  reverse), "stay domain-free — no imports of any host package," how to add a provider or a
  role, the scratchpad value-codec contract, and the config/env contract. One screen,
  imperative, skimmable.
- **`docs/*.md` as OKF-lite:** one concept per file, descriptive filenames, structural markdown
  (headings, tables, fenced code) over prose — exactly what makes retrieval work. Just drop the
  frontmatter and the reserved-file rules; a short hand-maintained `docs/README.md` is enough.
- **Why this over full OKF:** OKF earns its keep on a large, multi-author bundle where typed
  filtering and history matter. For one library the frontmatter and week-logs are overhead an
  agent doesn't need — small single-topic files plus a strong `README`/`AGENTS.md` entry point
  give it the same navigability for free.

### G. How to move and merge the docs — step by step

**1. Map source → destination.** Every core doc lands in exactly one place:

| Source (this bundle) | → Destination (new repo) |
| --- | --- |
| `packages/agent-kit/README.md` (the 476-line entry point: mental model, copy-paste checklist, worked example) | **`README.md`** — the base of the new root readme |
| `packages/llm-core/README.md` | folded **into `README.md`** as a short "The LLM core layer (`agent_kit._llm`)" section — not a separate file |
| `packages/agent-kit.md` → `## run_agent`, `## Module layout` | **`docs/orchestrator.md`** |
| `packages/agent-kit.md` → `## The context store` | **`docs/context-store.md`** |
| `packages/agent-kit.md` → `## Prompt rendering`, `## Errors`, `## Tests` | fold into `docs/orchestrator.md` (or a short `docs/prompts.md` if you prefer) |
| `packages/llm-core.md` → `## Modules` (providers) | **`docs/providers.md`** |
| `packages/llm-core.md` → tool-loop parts of `## Modules` | **`docs/tool-loop.md`** |
| `packages/llm-core.md` → `## Loop-bound clients` | fold into `docs/providers.md` |
| **merge** `llm-core.md` `## Scratchpad working memory` + `agent-kit.md` `## Scratchpad persistence` | **`docs/scratchpad.md`** |
| **merge** `llm-core.md` `## Tracing…` + `agent-kit.md` `## Tracing` + trimmed `observability.md` | **`docs/observability.md`** |
| **merge** `agent-kit.md` `## LLM role/provider config` + trimmed `reference/llm-config.md` | **`docs/config.md`** |
| — (write new) | **`AGENTS.md`**, **`docs/README.md`** |

**2. Merge the three doubled-up concepts** — lead with the lower layer, then the orchestration on top:

- **`docs/scratchpad.md`:** open with the primitive (`Scratchpad`/`Handle`, `remember`/`recall`,
  the board — now `agent_kit._llm.scratchpad`), then the cross-turn half from agent-kit
  (persistence, the value `ScratchpadCodec`, restore-on-plan). One narrative, no repetition.
- **`docs/observability.md`:** the trace *hook* and record schema (from llm-core, "the hook,
  never the writer"), then the *recorder + scopes + wiring invariant* (from agent-kit and the
  trimmed observability doc). Keep the invariant — "`install_file_tracing()` once at startup,
  `trace_context` at each unit-of-work boundary" — stated once, prominently.
- **`docs/config.md`:** the config *document* schema and role/provider model (from agent-kit),
  then the *env-var registry* and precedence table (from the trimmed llm-config doc). Drop the
  `embedding:` passthrough sections — host concern.

**3. Convert each file (OKF → plain markdown):**

- Delete the YAML frontmatter block entirely.
- Rewrite links: `/`-absolute bundle links between core docs become new-repo relative
  (`./config.md`, `../README.md`); links to domain docs that **stay here** (`/retrieval/*`,
  `/data-model/*`, …) are now dangling — drop them or reword to prose.
- Fix the README's `../llm-core/README.md` link — that sibling path no longer exists.
- Retitle: `# llm-core Package (\`packages/llm-core/\`)` → the concept name; drop the
  `(packages/…)` path suffixes. Module headings citing `packages/llm-core/src/llm_core/…` now
  cite `src/agent_kit/_llm/…`; `packages/agent-kit/src/agent_kit/…` → `src/agent_kit/…`.
- Present tense, and strip any "this repo" / corpus-specific phrasing — the library is
  domain-free, its docs should read that way.

**4. Sanity check:** each `docs/*.md` is one concept, carries no frontmatter, and every link
resolves inside the new repo. `README.md` + `AGENTS.md` + `docs/README.md` between them link to
every file in `docs/` — that hand-list is what replaces OKF's generated `index.md`.

## Definition of done

- **New repo:** `uv sync` + `uv run pytest` green (all former `llm-core` and `agent-kit` tests,
  imports repointed to `agent_kit._llm`); `v0.1.0` tagged and pushed.
- **This repo, after B + C:**
  - No `from llm_core…` imports remain (`grep -rn 'llm_core' packages scripts` is empty).
  - `uv lock` succeeds; `uv.lock` shows `agent-kit` sourced from the git commit for `v0.1.0`
    (grep the lock for the repo URL). No `llm-core` distribution appears.
  - `uv sync` clean.
  - `uv run ruff check` clean; `uvx ty@latest check` clean — any unresolved import on
    `agent_kit` means a symbol wasn't re-exported or a source line was missed.
  - `uv run pytest` green across `ai`, `agents`, `api`, `worker-*`, `scripts`.
- **Reproducibility proof:** on a second checkout (or after `rm -rf .venv`), `uv sync` restores
  the exact pinned commit with git access alone — no wheel, no local path.

## Follow-ups

- Docs: the bundle still describes both as in-repo packages — [packages index](/packages/index.md),
  [llm-core](/packages/llm-core.md), [agent-kit](/packages/agent-kit.md). Refresh once the
  rewire lands (the two package concepts likely merge into one).
- Version bumps: cutting `v0.2.0` = bump the package `version`, tag, then bump the `tag =` in
  this repo's single source line and `uv lock`.
- Config defaults: fold "ship a built-in default `llm_config` when the host has none" into the
  new repo, per the deferred gap in section D.
