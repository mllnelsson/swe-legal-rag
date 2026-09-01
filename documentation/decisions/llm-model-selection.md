---
type: Decision
title: Per-task LLM model and provider selection
description: Why each task gets its own model and provider, declared in llm_config.yaml rather than in environment variables or code.
tags: [llm, model, provider, berget, config, cost]
timestamp: 2026-09-01T00:00:00Z
---

# Per-task LLM model and provider selection

**Status:** Accepted — six roles (`structured`, `summarize`, `chat`, `orchestrate`,
`read`, `sql`) on Berget.ai by default, declared in
[`llm_config.yaml`](/reference/llm-config.md)

Embedding choices have their own records ([model](/decisions/embedding-model.md),
[hosting](/decisions/embedding-hosting.md),
[dimension](/decisions/embedding-dimension.md)). The LLM side had none — the reasoning
lived only as prose in the [ai package](/packages/ai.md) doc. This record is that gap.

## The problem

`agent_kit.llm.LLMConfig` carries a single `model` field: one process-wide model for every
call. But the tasks in this system have genuinely different cost/quality profiles, and
they run at wildly different volumes.

| Role | Used by | Volume | Wants |
|---|---|---|---|
| `structured` | [query decomposition](/retrieval/chat-agent.md), [metadata](/pipeline/metadata.md) and [entity extraction](/pipeline/extract.md), rerank | Once per document at ingestion, plus once per query | Cheap, reliable JSON-schema output |
| `summarize` | [document summarisation](/pipeline/chunk.md) for contextual chunking | Once per ingested document, sees whole documents | Context length over price |
| `chat` | [the conversational agent's](/retrieval/chat-agent.md) plan step and answer synthesis | A handful per day, streaming, user-facing | The strongest model here; it is not run at ingestion scale |
| `orchestrate` | [the conversational agent's](/retrieval/chat-agent.md) executor tool loop | Several calls per turn, on demand | Reliable multi-turn tool-calling, no prose — the mechanical half of a chat turn, once `chat` has set the strategy |
| `read` | the conversational agent's document-reading sub-agent | Low volume, on demand | Context length — sees one whole decision per call |
| `sql` | [the SQL agent](/packages/agents.md) | Low volume, on demand | Reliable multi-turn tool-calling; not the hard part of text-to-SQL, so no need for the strongest model — see [the grounding decision](/decisions/sql-agent.md) |

Running one model across all six either overpays for extraction or underpowers
synthesis. With a [<$5/month LLM budget](/reference/cost-estimate.md) the difference
matters.

## Decision

**A role is a named entry in `llm_config.yaml`, not a Python symbol.** The file declares
providers once and lets each role reference one by name, inheriting anything it does
not override:

```yaml
providers:
  berget: {kind: openai_compatible, base_url: https://api.berget.ai/v1, api_key_env: BERGET_API_KEY}
  gemini: {kind: gemini, api_key_env: GEMINI_API_KEY}
defaults:
  provider: berget
roles:
  structured: {model: mistralai/Mistral-Small-3.2-24B-Instruct-2506}
  summarize:  {model: google/gemma-4-31B-it}
  chat:       {model: zai-org/GLM-5.2}
```

Consequences, in order of how much they matter:

1. **A role may name its own provider.** Running summarisation on Gemini while chat
   stays on Berget is a two-line YAML edit. Under the previous design — three
   `LLM_MODEL_*` environment variables overriding only `model` — it was not expressible
   at all, because `LLM_PROVIDER` was process-wide.
2. **Adding a role is a YAML-only change.** `ai.create_llm_provider("rerank")` works as
   soon as `rerank:` exists in the file. `ROLE_STRUCTURED`/`ROLE_SUMMARIZE`/`ROLE_CHAT`
   are constants for the three roles that have call sites today, not a closed set.
3. **A role may override `temperature`, `max_tokens` and `stream_usage` too**, not just
   `model`. Extraction wanting `temperature: 0.0` while synthesis wants something warmer
   is now sayable.
4. **The base URL and key variable for a host are declared once** and shared by the LLM
   roles and the [embedder](/decisions/embedding-hosting.md), which reuses the same
   Berget account. Previously the Berget base URL was hardcoded in two separate
   factories.

Environment variables still win over the file — see the
[precedence rules](/reference/llm-config.md#precedence). The file is the checked-in
default; the environment is the deployment override.

## Why Berget for all three by default

The same reasoning as [embedding hosting](/decisions/embedding-hosting.md), and
deliberately the same account:

- **One account, one key, one base URL** already provisioned for embeddings. A second
  provider is infrastructure to obtain, rotate and pay for.
- **EU data residency**, which matters for Swedish legal documents.
- **OpenAI-API-compatible**, so it needs no provider class of its own — it is a
  `providers:` entry with `kind: openai_compatible`. A third host (Groq, Together, a
  local vLLM) is likewise config, not code.

**Gemini remains fully supported** as a `kind: gemini` provider, per-role or globally.
Note that the Berget model IDs above will not resolve against Gemini's API, so switching
a role to Gemini means changing its `model:` in the same edit — and
`gemini-2.0-flash` was shut down 2026-06-01, so pick a live name (see
[LLM pricing](/reference/llm-pricing.md)).

## `LLM_MODEL` is deliberately ignored

`LLM_MODEL` (singular) predates per-task roles. It is still a field on
`agent_kit.llm.LLMConfig`, but **role resolution never consults it**: allowing it through
would silently collapse all three roles onto one model, which is exactly what this
design exists to prevent. The per-role override is `LLM_MODEL_<ROLE>`, derived from the
role name, so a newly declared role gets one for free.

`LLM_PROVIDER` is the one environment variable that *does* still flatten every role onto
one host. That is intentional — it is the global kill-switch — but it is also a trap,
because the YAML continues to read as though the per-role choice is in effect. The
loader logs a `WARNING` whenever it masks a role's declared provider.

## Trade-offs

- **One more file to keep in sync with reality.** Mitigated by making a missing or
  malformed file fatal at startup rather than falling back to built-in defaults: silent
  fallback is how the documented configuration and the running one drifted apart before
  (see [the log](/log.md)).
- **Two places to look** for a value — the file and the environment — until the
  overrides are removed from `.env`. The [env-var registry](/reference/llm-config.md)
  is the single list of what can override what.
- **Model IDs are provider-specific**, so a role's `provider:` and `model:` must change
  together. Nothing validates a model name against a host; a wrong pairing surfaces as a
  provider error on first call.

## Options considered

| Option | Per-role provider | Add a role | Verdict |
|---|---|---|---|
| **`llm_config.yaml` with a provider registry** | Yes | YAML edit | **Selected** |
| Status quo — three `LLM_MODEL_*` env vars | No — `LLM_PROVIDER` is process-wide | New env var + new pydantic field + new factory function | Superseded |
| Per-role env vars for every field (`LLM_TEMPERATURE_CHAT`, …) | Yes, but | Combinatorial env-var sprawl; no place for comments or rationale | Not selected |
| Model assignment in Python constants | Yes | Code change and redeploy to swap a model | Not selected — model choice changes far more often than the code around it |

## Re-evaluation triggers

Revisit if:

- A task needs a model whose API is neither OpenAI-compatible nor Gemini — that is a new
  provider class in the external `agent-kit` package, not a config entry.
- Per-role secrets diverge such that one `api_key_env` per provider is not enough.
- Roles proliferate to the point that the flat `roles:` map wants grouping.
- Berget publishes rates that change the cost argument for the role split (none are
  published in this repo today — see [LLM pricing](/reference/llm-pricing.md)).
