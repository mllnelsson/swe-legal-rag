---
type: Reference
title: llm_config.yaml — LLM and Embedding Configuration
description: The single source of truth for which model and provider each LLM role and the embedder use — file format, precedence rules against environment variables, and the full env-var registry.
resource: llm_config.yaml
tags: [llm, config, yaml, provider, embedding, precedence]
timestamp: 2026-08-01T15:02:17Z
---

# llm_config.yaml — LLM and Embedding Configuration

`llm_config.yaml`, at the repo root, is **the single source of truth for which model
and which provider each task uses.** It replaces the per-task model env vars that
used to live only in `.env.example` and package docs — those still exist, but now as
*overrides* of the file, not as the primary source. Loaded by
[`ai.llm_config`](/packages/ai.md); resolution and precedence live there, this page
documents the contract.

Adding a task with its own model is a YAML edit. No Python change is required.

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
  query_prefix: "query: "
  passage_prefix: "passage: "
```

| Section | Purpose |
|---|---|
| `version` | Must equal `1` — the only version this build understands. Load fails otherwise. |
| `providers` | Named hosts. `kind` is `openai_compatible` or `gemini` — the client implementation dispatched on. `api_key_env` names the environment variable holding that host's key; `base_url` is optional (only `openai_compatible` needs one, and it falls back to `llm_core.BERGET_BASE_URL` if omitted). |
| `defaults` | Inherited by every role that omits the field: `provider`, `temperature`, `max_tokens`, `stream_usage`. |
| `roles` | One entry per task. `model` is required; `provider`/`temperature`/`max_tokens`/`stream_usage` are optional per-role overrides of `defaults`. |
| `embedding` | The embedder's `provider` (a `providers` name, or the literal `"local"` for in-process `sentence-transformers`), `model`, `dimension`, and the retrieval `query_prefix`/`passage_prefix` pair. |

Every document model uses `extra="forbid"` — a typo'd or unrecognized key fails to
load rather than silently doing nothing. A missing file is fatal
(`LLMConfigNotFoundError`): there is no built-in fallback model set, deliberately,
because a silent fallback is how the documented models and the ones actually running
have already drifted apart once (see [LLM model selection](/decisions/llm-model-selection.md)).

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

1. Add an entry under `roles:` in `llm_config.yaml` with at least `model:`.
2. Call `ai.create_llm_provider("<your-role-name>")` from wherever the task needs a
   provider.

No Python constant is required — `ai.providers.roles.ROLE_STRUCTURED` /
`ROLE_SUMMARIZE` / `ROLE_CHAT` exist only because those three roles have call sites
today, not because the set of valid roles is closed. Requesting an undeclared role
raises `UnknownLLMRoleError`.

The role automatically gets its own override variable, `LLM_MODEL_<ROLE_UPPER>` (role
name upper-cased, `-` replaced with `_`) — computed from the role name, not
hand-registered, via `ai.llm_config.role_model_env_var`.

## Pointing a role at a different provider

Add `provider: <name>` under that role, where `<name>` is a key declared under
`providers:`. A second `openai_compatible` host needs no new provider class — only a
new `providers:` entry naming its `base_url` and `api_key_env` (see
[llm-core](/packages/llm-core.md)). Loading fails with a clear message if the name
is not declared.

## Env-var registry

| Variable | Scope | Effect |
|---|---|---|
| `LLM_CONFIG_PATH` | Global | Points at a config file directly, skipping the walk-up-from-cwd discovery. A missing file at this path is fatal. |
| `LLM_PROVIDER` | Every role | Overrides every role's provider `kind`, flattening them onto one host. Logs a warning when it masks a role's own `provider:`. |
| `LLM_MODEL_<ROLE>` | One role | Overrides that role's `model`. Exists for free for any role declared in the YAML — `LLM_MODEL_STRUCTURED`, `LLM_MODEL_SUMMARIZE`, `LLM_MODEL_CHAT` today. |
| `LLM_MODEL` | — | Deliberately ignored by role resolution. Pre-dates roles. |
| `LLM_TEMPERATURE` | Every role | Overrides `temperature` for whichever role is being resolved. |
| `LLM_MAX_TOKENS` | Every role | Overrides `max_tokens`. |
| `LLM_STREAM_USAGE` | Every role | Overrides `stream_usage` — turn off only if a host rejects the streaming-usage request parameter; it fails the whole call. |
| `LLM_BASE_URL` | Every role + embedding | Overrides the resolved provider's `base_url`. |
| `LLM_API_KEY` | Every role + embedding | Host-agnostic key override, read before the provider's own named variable (`BERGET_API_KEY`/`GEMINI_API_KEY`). |
| `BERGET_API_KEY`, `GEMINI_API_KEY` | Named provider | The normal source of a provider's key — named per-provider by `providers.<name>.api_key_env`, never read from the YAML. |
| `EMBEDDING_PROVIDER` | Embedding | Overrides `embedding.provider`. |
| `EMBEDDING_MODEL` | Embedding | Overrides `embedding.model`. |
| `EMBEDDING_DIMENSION` | Embedding | Overrides `embedding.dimension`. Must agree with `embedding.dimension` and the `chunks.embedding` column width — see [embedding dimension](/decisions/embedding-dimension.md). |

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
