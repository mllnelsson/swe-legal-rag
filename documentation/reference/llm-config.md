---
type: Reference
title: llm_config.yaml — LLM and Embedding Configuration
description: The single source of truth for which model and provider each LLM role and the embedder use — file format, precedence rules against environment variables, and the full env-var registry.
resource: llm_config.yaml
tags: [llm, config, yaml, provider, embedding, precedence]
timestamp: 2026-08-02T00:00:00Z
---

# llm_config.yaml — LLM and Embedding Configuration

`llm_config.yaml`, at the repo root, is **the single source of truth for which model
and which provider each task uses.** It replaces the per-task model env vars that
used to live only in `.env.example` and package docs — those still exist, but now as
*overrides* of the file, not as the primary source. Loaded by
[`ai.llm_config`](/packages/ai.md); resolution and precedence live there, this page
documents the contract.

Swapping a task's model is a YAML edit. **Adding** a task needs both an entry
under `roles:` here and a matching `LLMRole` member in
`ai.providers.roles` — see [adding a role](#adding-a-role).

## File format

```yaml
version: 1

providers:
  berget:
    kind: openai_compatible
    base_url: https://api.berget.ai/v1
    api_key_env: BERGET_API_KEY
  gemini:
    kind: gemini
    api_key_env: GEMINI_API_KEY

defaults:
  provider: berget
  temperature: 0.0
  max_tokens: null
  stream_usage: true

roles:
  structured:
    model: mistralai/Mistral-Small-3.2-24B-Instruct-2506
  summarize:
    model: mistralai/Mistral-Medium-3.5-128B
    max_tokens: 256            # coarse stop on runaway generation — see below
  chat:
    model: zai-org/GLM-5.2
    # provider: gemini        # optional per-role override of defaults.provider
    # temperature: 0.2
    # max_tokens: 4096
    # stream_usage: false

embedding:
  provider: berget            # a name from `providers`, or the literal "local"
  model: intfloat/multilingual-e5-large
  dimension: 1024
  # No `max_sequence_tokens` key — deliberately. See below.
  query_prefix: "query: "
  passage_prefix: "passage: "
```

| Section | Purpose |
|---|---|
| `version` | Must equal `1` — the only version this build understands. Load fails otherwise. |
| `providers` | Named hosts. `kind` is a `llm_core.ProviderKind` — `openai_compatible`, `gemini` or `none` — the client implementation dispatched on. `api_key_env` names the environment variable holding that host's key, and is **required for every kind except `none`**, which has no host to send one to. `openai_compatible` also requires `base_url`: there is no built-in default, and a host missing either raises `llm_core.MissingCredentialError` at construction. |
| `defaults` | Inherited by every role that omits the field: `provider`, `temperature`, `max_tokens`, `stream_usage`. |
| `roles` | One entry per task. `model` is required; `provider`/`temperature`/`max_tokens`/`stream_usage` are optional per-role overrides of `defaults`. |
| `embedding` | The embedder's `provider` (a `providers` name, or the literal `"local"` for in-process `sentence-transformers`), `model`, `dimension`, and the retrieval `query_prefix`/`passage_prefix` pair. Naming a provider whose `kind` has no embeddings client (`gemini` and `none`) raises `ai.errors.UnsupportedEmbeddingBackendError` at resolution time, naming the offending key. |

Every document model uses `extra="forbid"` — a typo'd or unrecognized key fails to
load rather than silently doing nothing. A missing file is fatal
(`LLMConfigNotFoundError`): there is no built-in fallback model set, deliberately,
because a silent fallback is how the documented models and the ones actually running
have already drifted apart once (see [LLM model selection](/decisions/llm-model-selection.md)).

## `summarize.max_tokens`

The `summarize` role sets `max_tokens: 256`, unlike the other roles which leave it at
`defaults.max_tokens: null`. The document summary this role produces is prepended to
every chunk before embedding, so an unbounded summary silently displaces chunk text
inside the embedding model's window rather than overflowing it. `256` is a coarse stop on
runaway generation, sized so a compliant ~60-word Swedish summary is never cut by it —
it is not the enforced ceiling. That ceiling is
[worker-chunk](/pipeline/chunk.md)'s `truncate_summary()`, applied after the LLM call,
because a provider-side cut at `max_tokens` lands mid-word and mid-sentence, which a
purpose-built truncation function does not. See [embedding
window](/decisions/embedding-window.md) for the full budget this protects.

## No sequence-window key under `embedding:`

`embedding.dimension` is declared because a second artefact — the `chunks.embedding`
column — must independently agree with it, and nothing else can reconcile the two. The
embedding model's max sequence length has no such counterpart: nothing outside the
process is constrained by it, so a declared `max_sequence_tokens` key could only ever
drift out of step with the tokenizer that actually enforces it. Instead,
[worker-chunk](/pipeline/chunk.md) and [worker-embed](/pipeline/embed.md) read it off
`AutoTokenizer.from_pretrained(embedding.model).model_max_length` at startup via
`ai.create_embedding_ruler()` and `ai.verify_embedding_window()`. See [embedding
window](/decisions/embedding-window.md).

## API keys are never in the YAML

A provider entry names the **environment variable** its key comes from
(`api_key_env`); the key's value always stays in `.env` or Secret Manager. Nothing in
`llm_config.yaml` is a secret, so the file is safe to commit and to diff in a PR.

## Precedence

Highest wins first:

1. **Environment variable**
2. **The role's own entry** (or `embedding:` for the embedder)
3. **`defaults`**
4. **The field default on `llm_core.LLMConfig`**

This is the **opposite** of pydantic-settings' native ordering, where an explicit
init keyword argument beats an environment variable. The loader achieves the reversal
by *withholding* the keyword argument whenever the corresponding environment variable
is set, letting `LLMConfig`'s own env-reading fill the field instead — see
`ai.llm_config._without_env_overrides`.

**`model` is the one field with a different rule**, because it must resist the
pre-existing global `LLM_MODEL` env var:

| For `model` | Wins |
|---|---|
| `LLM_MODEL_<ROLE>` is set | that value |
| otherwise | the role's `model:` in the YAML |

`LLM_MODEL` (singular) is **never consulted** for role resolution. It predates
per-task roles and would collapse every role onto one model if it were — see
[why `LLM_MODEL` is ignored](/decisions/llm-model-selection.md#llm_model-is-deliberately-ignored).

Every other field (`provider`, `temperature`, `max_tokens`, `stream_usage`,
`base_url`, `api_key`) follows the four-level list above exactly: the matching
environment variable, if set, overrides the role and `defaults` regardless of which
role is being resolved — including `LLM_PROVIDER`, which is process-wide and
therefore flattens **every** role onto one host. `ai.llm_config` logs a `WARNING`
when a set `LLM_PROVIDER` masks a role's own `provider:` entry, because the YAML
still reads as though the per-role choice is in effect while the environment quietly
overrides it. Unset `LLM_PROVIDER` to let the file decide.

## Adding a role

The role set is **closed**, not YAML-only: both halves must exist and must agree.

1. Add a member to `ai.providers.roles.LLMRole` (a `StrEnum`; the value must match
   the key used in step 2).
2. Add a matching entry under `roles:` in `llm_config.yaml` with at least `model:`.
3. Call `ai.create_llm_provider(LLMRole.<YOUR_ROLE>)` from wherever the task needs a
   provider.

`resolve_role_config(role: str, ...)` — one layer below `create_llm_provider` — still
resolves an arbitrary string key out of the file, but `LLMRole` is the closed set code
actually asks for, which is what makes a misspelled role a type error rather than a
runtime `UnknownLLMRoleError`. Calling `resolve_role_config` directly with a role
undeclared in the YAML still raises `UnknownLLMRoleError`.

The role automatically gets its own override variable, `LLM_MODEL_<ROLE_UPPER>` (role
name upper-cased, `-` replaced with `_`) — computed from the role name, not
hand-registered, via `ai.llm_config.role_model_env_var`.

## Pointing a role at a different provider

Add `provider: <name>` under that role, where `<name>` is a key declared under
`providers:`. A second `openai_compatible` host needs no new provider class — only a
new `providers:` entry naming its `base_url` and `api_key_env` (see
[llm-core](/packages/llm-core.md)). Loading fails with a clear message if the name
is not declared.

## Running with no LLM

`kind: none` declares a provider that is configured to not exist. It resolves and
constructs with no `base_url` and no `api_key_env`, and raises
`llm_core.LLMDisabledError` if anything calls it. That ordering is the whole point: a
process whose LLM steps are switched off starts normally instead of dying on a
credential it will never use, which is otherwise what happens — every worker builds
its provider in `subscribe()`, before the first message.

Two ways to reach it:

```yaml
providers:
  off:
    kind: none          # no base_url, no api_key_env

roles:
  summarize:
    provider: off       # this role only
```

or `LLM_PROVIDER=none` in the environment, which disables **every** role at once and
needs no YAML change. The masking warning fires, correctly — that is exactly what is
happening.

What each pipeline step then does:

| Step | Behaviour |
|---|---|
| [crawl](/pipeline/crawl.md), [download](/pipeline/download.md), [parse](/pipeline/parse.md) | Unaffected — no LLM in the path |
| [metadata](/pipeline/metadata.md) | Starts. The rule-based pass runs; the LLM fallback raises and is caught, so the document is saved with whatever the regex pass found. Expect one warning per incomplete document |
| [extract](/pipeline/extract.md) | `EXTRACT_STRATEGY=rule_based` builds nothing. The default fallback mode degrades to its regex half at startup, with a warning. `EXTRACT_STRATEGY=llm` refuses to start |
| [chunk](/pipeline/chunk.md) | Starts, then **fails every document**. The summary is prepended to every chunk, so there is no honest degraded mode — this is where a no-LLM run stops |
| [embed](/pipeline/embed.md) | Unaffected when `embedding.provider` is `local`, which needs no host and no key. A hosted embedder still needs its key; `kind: none` is refused for `embedding.provider` |
| [API](/packages/api.md) | Starts; `/api/chat` fails at the first model call |

`ai.llm_role_is_disabled(role)` answers "is this role `kind: none`?" without building
a provider, for the callers that have a real no-model path and want to choose it at
startup, where every other provider decision is made. worker-extract is the only one
today. Everything else just builds the provider and lets it refuse.

See [live testing](/playbooks/live-testing.md) for the commands.

## Env-var registry

| Variable | Scope | Effect |
|---|---|---|
| `LLM_CONFIG_PATH` | Global | Points at a config file directly, skipping the walk-up-from-cwd discovery. A missing file at this path is fatal. |
| `LLM_PROVIDER` | Every role | Overrides every role's provider **kind** (`openai_compatible`, `gemini` or `none` — a `ProviderKind` value, not a `providers:` name), flattening them onto one host. Logs a warning when it masks a role's own `provider:`. `LLM_PROVIDER=none` is the process-wide LLM off switch — see [running with no LLM](#running-with-no-llm). |
| `LLM_MODEL_<ROLE>` | One role | Overrides that role's `model`. Exists for free for any role declared in the YAML — `LLM_MODEL_STRUCTURED`, `LLM_MODEL_SUMMARIZE`, `LLM_MODEL_CHAT` today. |
| `LLM_MODEL` | — | Deliberately ignored by role resolution. Pre-dates roles. |
| `LLM_TEMPERATURE` | Every role | Overrides `temperature` for whichever role is being resolved. |
| `LLM_MAX_TOKENS` | Every role | Overrides `max_tokens`. |
| `LLM_STREAM_USAGE` | Every role | Overrides `stream_usage` — turn off only if a host rejects the streaming-usage request parameter; it fails the whole call. |
| `LLM_BASE_URL` | Every role + embedding | Overrides the resolved provider's `base_url`. There is no built-in default any more — an `openai_compatible` provider with neither this nor a YAML `base_url` refuses to start (`MissingCredentialError`). |
| `LLM_API_KEY` | Every role + embedding | Host-agnostic key override. When unset, the key comes from whichever variable the resolved provider's `api_key_env` names (`BERGET_API_KEY`/`GEMINI_API_KEY` today) — `llm_core.LLMConfig` itself carries only the one `api_key` field, not a named field per host. |
| `BERGET_API_KEY`, `GEMINI_API_KEY` | Named provider | The normal source of a provider's key — named per-provider by `providers.<name>.api_key_env`, never read from the YAML. These are ordinary vendor-named env vars; nothing about them is special-cased in code beyond the `api_key_env` indirection. |
| `EMBEDDING_PROVIDER` | Embedding | Overrides `embedding.provider`. Takes an `EmbeddingBackend` **kind** (`openai_compatible` or `local`) rather than a `providers:` name — setting it to a host name like `berget` is not valid. |
| `EMBEDDING_MODEL` | Embedding | Overrides `embedding.model`. |
| `EMBEDDING_DIMENSION` | Embedding | Overrides `embedding.dimension`. Must agree with `embedding.dimension` and the `chunks.embedding` column width — see [embedding dimension](/decisions/embedding-dimension.md). |
| `EMBEDDING_WINDOW_OVERRIDE` | Embedding | **Overrides nothing in the file** — there is no `embedding:` key for the sequence window, by design. Set it and no tokenizer is loaded: the window is this number and chunk sizes are estimated from character counts, roughly halving them. For a process that cannot reach the tokenizer; the number's correctness is the operator's, and it is logged at WARNING. See [embedding window](/decisions/embedding-window.md). |

All of these are optional. Leave them unset in `.env` unless deliberately overriding
the file — a stale value left over from a previous experiment silently wins over the
checked-in default and is the most common source of confusion with this system.

## Changing the embedding prefixes

`embedding.query_prefix` and `embedding.passage_prefix` are the two sides of an
asymmetric embedding model's retrieval convention (e5's `"query: "` /
`"passage: "`). Both are read from the same file by
[`ai.get_embedding_prefixes()`](/packages/ai.md), so the query side (used by the
[retrieval agent](/retrieval/agent.md)) and the passage side (used by
[worker-embed](/pipeline/embed.md)) cannot drift apart the way they once did. Set
both to `""` for a model that does not use prefixes (bge-m3, jina).

**Changing either value invalidates every stored embedding** — it changes what gets
embedded, not just how it is labelled. Clear `chunks.embedding` and re-run the embed
step; see [live testing](/playbooks/live-testing.md).
