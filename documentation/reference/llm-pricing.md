---
type: Reference
title: LLM Pricing Prerequisites
description: Verified per-token rates and the rules for applying them when analyzing LLM trace records. Reference data, not implemented anywhere in the repo.
tags: [observability, cost, pricing, llm]
timestamp: 2026-08-13T00:00:00Z
---

# LLM Pricing Prerequisites

This concept holds the **verified rates and the rules for applying them**. It is
reference data for whoever analyzes the traces — there is deliberately no rate
table in the codebase. How records are captured and correlated is
[LLM Observability](/observability.md).

## Why there is no pricing code

A core project goal is seeing how cheap the system can run ([PRD](/prd.md): <$5/month
LLM budget). Every LLM call is written to a trace record holding the full
prompt/response, token counts and latency.

The record carries the served `model` and the provider's `usage`. That is the complete
raw material, and cost is a pure function of it. Pricing is therefore an **analysis
question**, answered when the traces are analyzed, with whatever tool the analysis
uses — not something the pipeline computes, stores, or ships a CLI for.

Two things follow, and both are the point:

- **Rates can be corrected.** A rate that was wrong, or absent, when a call happened
  applies to that call anyway, because it is applied on read. Nothing needs rewriting.
- **The repo carries no rate table to drift.** Rates change; a hard-coded table would
  need re-verifying against this page forever. The verified numbers live here, dated.

## Source of truth

Prices come from Google's official Gemini API pricing page:
<https://ai.google.dev/gemini-api/docs/pricing>.

- Use the **paid tier, standard** rates (not batch — the pipeline makes interactive
  calls).
- Use the **text** input rate. The pipeline sends text only; audio/video rates,
  context-caching rates, and cache-storage rates are out of scope. If context caching or
  batch calls are ever adopted, the rules here must be extended first.
- Re-verify **whenever the configured Gemini model changes**, and record the date below.

These rates apply to whichever roles use a `kind: gemini` provider — which can now be
some roles and not others, so a single run's traces may mix priced and unpriced models.

## Berget rates are not known

The default provider is Berget (see [llm_config.yaml](/reference/llm-config.md)), and
**no Berget rate is published in this repo**. Guessing one would be worse than reporting
nothing, so the models this project runs by default have no rate here:

| Model | Role |
|---|---|
| `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | `roles.structured` |
| `mistralai/Mistral-Medium-3.5-128B` | `roles.summarize`, `roles.read`, `roles.sql` |
| `zai-org/GLM-5.2` | `roles.chat` |

Which model fills each role is configurable, so confirm against `llm_config.yaml` (and
any `LLM_MODEL_<ROLE>` override in the environment) before pricing a run. The trace
records the model the provider **says it served**, which is the authoritative value.

`intfloat/multilingual-e5-large` (`embedding.model`) is not in this table: the shipped
`embedding.provider` is `local` — in-process `sentence-transformers`, no API call — and
[local embeddings are deliberately not traced](/observability.md), so they contribute
exactly zero to a question's cost regardless of pricing. Only a deployment that switches
`embedding.provider` to `berget` would need a rate for it, and that configuration is not
the default this table describes.

**Consequence:** on the out-of-the-box configuration, cost questions are answerable in
*tokens* only. Tokens are always recorded, so obtaining a Berget rate later prices every
trace already written.

## Verified prices (checked 2026-06-13)

| Model prefix | Input USD / 1M tokens | Output USD / 1M tokens | Note |
|---|---|---|---|
| `gemini-2.5-flash-lite` | 0.10 | 0.40 | Recommended Gemini default — same price point as the old 2.0-flash |
| `gemini-2.5-flash` | 0.30 | 2.50 | |
| `gemini-2.0-flash` | — | — | **Shut down 2026-06-01. Calls fail.** |
| `gemini-2.0-flash-lite` | — | — | **Shut down 2026-06-01. Calls fail.** |

No context-length pricing tiers apply to these models (verified on the pricing page);
a flat per-token rate is correct. If Google introduces tiered pricing for an adopted
model, the analysis must account for it rather than approximate with the base rate.

> **When running on Gemini,** pick a live model — `gemini-2.5-flash-lite` matches the
> price of the shut-down `gemini-2.0-flash`. The repo default provider is now Berget, so
> the historical "default is the shut-down `gemini-2.0-flash`" hazard no longer applies
> to the out-of-the-box configuration.

## Rules for applying these rates

- **Units:** USD per 1M tokens, input and output priced separately.
- **Use a decimal type, never a float.** A float does not round-trip a decimal and
  drifts once thousands of sub-cent calls are summed. Eight decimal places is a sensible
  floor, since a single cheap call costs well under a cent.
- **Match on model-name prefix, longest first,** against the model the API *returned*
  (the record's `model`), not the configured name. The returned string carries suffixes
  (`-001`, preview tags) that prefix matching absorbs, and longest-first is required so
  `gemini-2.5-flash-lite` does not match the `gemini-2.5-flash` row.
- **Match case-insensitively.** Berget model ids are mixed-case.
- **Unknown model ⇒ unpriced, never a guess and never a zero.** A total containing
  unpriced calls is a floor, not a total, and should be labelled as one.
- **`usage: null` and `output_tokens: null` mean "not reported", not zero.** Embeddings
  never report output tokens. Treating either as zero silently under-reports.
- **Failed calls still cost.** `success: false` records carry usage and are billed;
  exclude them only deliberately.

## Costing traces

Records are plain JSONL — one object per flushed batch under
`{LLM_TRACE_KEY_PREFIX}/{date}/`. Extract the two fields that matter and price them
however the analysis is being done:

```bash
# every call's model and tokens, for one day
cat data/llm-traces/2026-07-30/*.jsonl \
  | jq -r '[.context.source, .model, .usage.input_tokens,
            .usage.output_tokens] | @tsv'

# tokens by model, the input to any cost calculation
cat data/llm-traces/2026-07-30/*.jsonl \
  | jq -s 'group_by(.model) | map({model: .[0].model, calls: length,
           input: (map(.usage.input_tokens // 0) | add),
           output: (map(.usage.output_tokens // 0) | add)})'

# one chat question, end to end
cat data/llm-traces/2026-07-30/*.jsonl \
  | jq -r --arg i "<uuid>" 'select(.context.interaction_id == $i)
      | [.context.source, .model, .usage.input_tokens,
         .usage.output_tokens] | @tsv'
```

The `<uuid>` is the value of the `X-Interaction-Id` response header, or the id
logged by the API. This selects every source under one `interaction_id`,
including the SQL sub-agent's records when the turn reached for `query_corpus`
— `run_chat_agent` and `run_sql_agent` both inherit the caller's id rather than
minting their own, so a turn that ran both the orchestrator and a counting
question is one sum, not two. See
[correlation](/observability.md#correlation--the-wiring-invariant).

On GCS, `gsutil cat 'gs://<bucket>/llm-traces/2026-07-30/*.jsonl'` substitutes for
`cat`.

## Maintenance checklist

When changing the model (do these in the same change):

1. Check the pricing page; add the rate and the date checked to the table above.
2. Confirm the model has no context-length pricing tiers; note it here if it does.
3. Change the role's `model:` in [`llm_config.yaml`](/reference/llm-config.md) — that is
   the only place a default model is written down.
4. After the first live call, confirm the record's `model` and `usage` are non-null and
   that tokens are plausible against the provider's usage dashboard.

Per-interaction and per-document correlation is in
[LLM Observability](/observability.md).
