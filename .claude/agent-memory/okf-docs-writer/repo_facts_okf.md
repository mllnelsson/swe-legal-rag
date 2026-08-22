---
name: repo-facts-okf
description: Durable map of how this repo's code maps to the documentation/ OKF bundle — fan-out sets, placement rules, bundle conventions, and standing scope decisions.
metadata:
  type: project
---

A **map, not a journal**. Organised by topic so it stays a fixed size. Never add a
section per run; find the section a new fact belongs under and extend it, or
replace the line it makes wrong.

## Reading this repo's changes

- Worktrees are in use, and finished work often sits **uncommitted**. `git diff
  main...HEAD` and `git log main..HEAD` can both come back empty while a real
  change exists on disk. The moment the three-dot diff is empty, fall back to
  `git status` and a plain working-tree `git diff` — never conclude "nothing
  changed".
- Branch diffs here get large (240 KB on a 13-commit branch). Use `--stat` plus
  the commit messages to decide *which* concepts are affected, then pull code
  per-file. The commit messages in this repo are unusually explanatory; they are
  often better input than the diff.

## Fan-out sets — one code change, many docs that drift independently

The recurring failure is editing one of these and leaving the rest wrong. Each
line: **change → every doc that independently restates the same fact.**

| Change | Docs that all drift |
|---|---|
| New `documents.*` column the crawl worker dedups on | `data-model/documents.md`, `data-model/indexes.md`, `data-model/design-notes.md`, `pipeline/crawl.md`, `reference/crawl-source.md` |
| New `LLMRole` member | `packages/ai.md` (role table **and** enum listing), `reference/llm-config.md` (env-var row + illustrative YAML), `decisions/llm-model-selection.md` (`Status:` role count + role/volume table) |
| Persistence changing on re-run (e.g. replace vs union-append) | the worker doc, the junction-table doc, `data-model/repositories.md` (Notable functions) |
| Provider/client construction change | `packages/llm-core.md`, `pipeline/worker-patterns.md`, `packages/ai.md` module table, and `testing.md` if it names the old mocking pattern |
| Storage/config default path change | grep the **literal old path** bundle-wide; it hard-codes into shell examples in `observability.md`, both playbooks, `reference/llm-pricing.md` |
| A Python name deleted or renamed | grep the **whole bundle** for it. Decision docs spell out implementation names for their own argument's sake and drift separately from the package doc they cross-link |
| Chat/SSE or frontend API surface | grep `frontend` bundle-wide — "the frontend is chat's client" has been restated in four files at once |

## Where a thing gets documented

- **Document *format*** (segmentation anchors, identifier spaces) →
  `reference/document-structure.md`. **The worker that relies on it** →
  `pipeline/*.md`. These are constantly confused.
- **Extraction rules** → `pipeline/extract.md`. **Table shape** →
  `data-model/*.md`. A tuning change to a rule-based extractor is never a
  data-model edit.
- **Wire contract** (request/response DTOs) → the `api/*.md` endpoint doc.
  **Module structure** → the `packages/*.md` doc. Same split as
  `api/search.md` vs `packages/api.md`.
- **What the modules do** → package doc. **Why, the rejected alternative, the
  trade-off** → a `decisions/*.md` doc. Both cross-link; neither absorbs the
  other.
- **A standalone operational script** → a numbered subsection of the playbook or
  concept it exercises, never its own concept file. Precedents:
  `run_agent.py` → `playbooks/live-testing.md` "Option D";
  `check_semantic_model.py` → `reference/semantic-model.md` "## The dev script".
- **A safety mechanism enforced in code** (an executor refusing until a
  precondition ran) is Decision-doc-worthy, not just package prose.
- **A change that reverses a previously recorded rationale** gets its own dated
  subsection inside the existing decision doc, not a silent edit to the original
  `Decision:` section. The reversal is the thing worth the paper trail.
- **A new agent** goes in `packages/agents.md` as its own section, not folded
  into `packages/ai.md` — an agent is a different kind of thing from a
  prompt/DTO/service toolkit even though it depends on one.
- **A `PromptTemplate` used via a tool loop** rather than through
  `ai/services.py` is the one exception to "every template has a service
  function" — call it out in `packages/ai.md`, or a reader scanning
  `ai/services.py` will not find it.

## documentation/frontend/

Three concepts, deliberately split — do not fold them back together:
`frontend/overview.md` (stack, routes, design provenance),
`frontend/honesty-rules.md`, `frontend/generated-types.md`
(`npm run gen:types` → committed `src/api/schema.d.ts`).

`honesty-rules.md` is scoped to claims backed by a `describe("rule N …")` block.
Those blocks live in **more than one test file** — find them with
`grep -rl 'describe("rule ' frontend/src`, currently three files including
`features/agent/agent-honesty-rules.test.tsx` and
`components/research/honesty-rules.test.tsx`. The doc claims rules 1..N with no
gaps and ships a grep to prove it, so the count and the no-gap claim must both be
re-checked whenever a rule lands:
`grep -rho 'describe("rule [0-9]*' frontend/src | sort -t' ' -k2 -n -u`.
A new honest-sounding frontend behaviour with **no** such test goes in
`frontend/overview.md`, not as a numbered rule.

`chat-events.ts` is hand-written, not generated — the chat endpoint is a
`StreamingResponse`, so `gen:types` never covers it.

## Bundle conventions

- `documentation/log.md` is the only `log.md`. Newest-first within a dated
  heading. It is very long — read only its head.
- Same-file anchors are an established convention. GitHub slugify: lowercase,
  strip backticks/parens/slashes/dots, keep underscores, spaces→hyphens.
  `` ## The semantic model (`agents/sql/_semantic_model.py`) `` →
  `#the-semantic-model-agentssql_semantic_modelpy`. Avoid headings containing
  `...` or a colon — the leftover double space makes the slug unpredictable;
  reword instead.
- Anchors are linked **across** files. Before rewording any heading, grep the
  bundle for its slug.
- Cosmetic edits (fixing a literal path in an example command) do **not** bump
  `timestamp`. Meaning changes do.

## Standing scope rules

- `documentation/prd.md` is a product decision. Do not bring it in line with what
  was built during a docs-sync pass — flag as Uncertain. **This is not absolute**:
  an invocation that gives line-by-line PRD edits is exactly the explicit ask that
  overrides it. Check what *this* invocation asked for rather than reflexively
  declining.
- Pre-existing drift unrelated to the diff: fix it in files you are already
  editing, leave it in files you are not, and flag it as Uncertain. Do not open a
  file solely to fix drift nobody asked about.
- Never delete a file outside `documentation/` on your own initiative, even when
  its own content says it is stale. The instructing prompt owns that.

## Two modes of invocation

1. **Map a diff to reader impact** — the default described in the agent
   definition.
2. **Pre-measured drift pass** — the prompt hands over facts already measured
   (SQL counts, specific wrong strings, line numbers). Trust them; do not
   re-derive. Line numbers drift and are a checklist, not gospel — grep for the
   wrong string instead. Ends in the same report.

In mode 2, a corpus-size change is **two treatments, not one find-and-replace**.
A number describing *current* state gets overwritten. A number that is *evidence
a past decision rested on* gets dated in place ("on the N-document sample as of
<date>") — rewriting it falsifies the record of why the decision was made. The
tell is an arrow: "X went from A to B" is historical; "X chunks in the corpus" is
current.

## Known recurring drift

- **The default embedding provider.** `llm_config.yaml` ships
  `embedding.provider: local` (sentence-transformers, in-process, no key).
  `BERGET_API_KEY` is for the LLM roles, not `worker-embed`. Docs claiming
  Berget is the default embedder have been fixed at least twice and recur —
  grep `embedding.*[Bb]erget` bundle-wide.
- `GET /healthz` (not `/health`) is the health route, defined inline in
  `create_app`. No concept doc of its own.
