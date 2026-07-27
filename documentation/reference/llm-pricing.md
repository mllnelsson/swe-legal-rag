---
type: Reference
title: LLM Pricing Prerequisites
description: The pricing rules and verified rate table that back write-time LLM cost tracking (binding for ai/_pricing.py).
tags: [observability, cost, pricing, llm]
timestamp: 2026-07-27T00:00:00Z
---

# LLM Pricing Prerequisites

This concept specifies the **rate table and matching rules** that
`ai/_pricing.py` implements. How records are captured and correlated is
[LLM Observability](/observability.md).

## Why cost tracking exists

A core project goal is seeing how cheap the system can run ([PRD](/prd.md): <$5/month
LLM budget). Every LLM call is written to a trace record in file storage holding the
full prompt/response, token counts, latency, and a write-time `estimated_cost_usd`
computed from the table below.

## Source of truth

Prices come from Google's official Gemini API pricing page:
<https://ai.google.dev/gemini-api/docs/pricing>.

- Use the **paid tier, standard** rates (not batch — the pipeline makes interactive
  calls).
- Use the **text** input rate. The pipeline sends text only; audio/video rates,
  context-caching rates, and cache-storage rates are out of scope. If context caching or
  batch calls are ever adopted, the pricing model here must be extended first.
- Prices must be re-verified **whenever the configured Gemini model changes** and
  whenever a builder touches `ai/_pricing.py`.

These rates apply when `LLM_PROVIDER=gemini`.

## Berget rates are not known

The default provider is Berget (see [local dev](/playbooks/local-dev.md)), and **no
Berget rate is published in this repo**. Guessing one would be worse than reporting
nothing, so the four models this project runs by default are deliberately absent from
the table:

| Model | Role |
|---|---|
| `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | `LLM_MODEL_STRUCTURED` |
| `mistralai/Mistral-Medium-3.5-128B` | `LLM_MODEL_SUMMARIZE` |
| `zai-org/GLM-5.2` | `LLM_MODEL_CHAT` |
| `intfloat/multilingual-e5-large` | Berget-hosted embeddings |

**Consequence:** on the out-of-the-box configuration every record carries
`estimated_cost_usd: null`, and cost questions are answerable in *tokens* only. Tokens
are the ground truth, so adding a rate later makes historical cost recomputable — see
[recomputing](#recomputing-cost-from-tokens). Adding one is a single line in `_PRICES`.

## Verified prices (checked 2026-06-13)

| Model prefix | Input USD / 1M tokens | Output USD / 1M tokens | Note |
|---|---|---|---|
| `gemini-2.5-flash-lite` | 0.10 | 0.40 | Recommended Gemini default — same price point as the old 2.0-flash |
| `gemini-2.5-flash` | 0.30 | 2.50 | |
| `gemini-2.0-flash` | — | — | **Shut down 2026-06-01. Do not seed; calls fail.** |
| `gemini-2.0-flash-lite` | — | — | **Shut down 2026-06-01. Do not seed; calls fail.** |

No context-length pricing tiers apply to these models (verified on the pricing page);
the table assumes a flat per-token rate. If Google introduces tiered pricing for an
adopted model, `estimate_cost_usd()` must be extended — do not approximate with the base
rate silently.

> **When running on Gemini,** pick a live model — `gemini-2.5-flash-lite` matches the
> price of the shut-down `gemini-2.0-flash`. The repo default provider is now Berget, so
> the historical "default is the shut-down `gemini-2.0-flash`" hazard no longer applies
> to the out-of-the-box configuration.

## Table semantics (binding for `ai/_pricing.py`)

- **Units:** USD per 1M tokens, input and output priced separately. Held as `Decimal`
  and serialized as a JSON **string** — never a float, which does not round-trip a
  Decimal and drifts when thousands are summed. Quantized to 8 decimal places, since a
  single cheap call costs well under a cent.
- **Keying:** model-name **prefix**, matched longest-prefix-first against the model
  string the API *returns* (`response.model` / `response.model_version`), not the
  configured name. The returned string can carry suffixes (e.g. `-001`, preview tags);
  prefix matching absorbs them. Longest-prefix-first is required so
  `gemini-2.5-flash-lite` wins over `gemini-2.5-flash` for lite models.
- **Matching is case-insensitive.** Berget model ids are mixed-case, and matching them
  case-sensitively would silently yield null costs forever.
- **Unknown model ⇒ `null` cost, never an error and never a guess.** Token counts are
  always stored regardless — they are the ground truth from which cost is recomputed.
  A null is not a zero; `"0.00000000"` means genuinely free.
- **Write-time freeze is intentional:** `estimated_cost_usd` records the price in effect
  when the call happened. Later price changes update the table for *future* calls only;
  existing records are not rewritten.

## Recomputing cost from tokens

If a rate was wrong or missing, recompute from the stored tokens rather than editing
history blindly. Records are append-only, so recomputation happens at read time:

```bash
# spend for a model that had no rate at write time (flash-lite: 0.10 in / 0.40 out)
jq -s 'map(select(.model | startswith("gemini-2.5-flash-lite")))
       | map((.usage.input_tokens // 0) * 0.10 + (.usage.output_tokens // 0) * 0.40)
       | add / 1000000' \
  data/pdfs/llm-traces/2026-07-27.jsonl
```

## Maintenance checklist

When changing the model or touching pricing (do these in the same change):

1. Check the pricing page; record the date checked in the table above.
2. Add/adjust the prefix entry in `ai/_pricing.py` (Decimal, per 1M tokens, standard
   text rates, lowercase prefix key).
3. Confirm the model has no context-length pricing tiers; if it does, extend
   `estimate_cost_usd()` first.
4. Update the model defaults in `.env.example` and the [local dev](/playbooks/local-dev.md)
   env listing if the default changes.
5. After the first live call, sanity-check one trace record: `estimated_cost_usd`
   non-null and plausible against the provider's usage dashboard.

## Follow-up queries (headline)

```bash
# LLM spend for one day (the budget question)
jq -s 'map(.estimated_cost_usd | select(. != null) | tonumber) | add' \
  data/pdfs/llm-traces/2026-07-27.jsonl

# spend by model
jq -s 'group_by(.model) | map({model: .[0].model, calls: length,
        tokens: (map(.usage.total_tokens // 0) | add),
        usd: (map(.estimated_cost_usd | select(. != null) | tonumber) | add)})' \
  data/pdfs/llm-traces/2026-07-27.jsonl
```

Per-interaction and per-document cost queries are in
[LLM Observability](/observability.md).
