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
full prompt/response, token counts and latency. The record carries **no cost field** —
cost is applied on read by `scripts/llm_cost.py` from the table below.

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

**Consequence:** on the out-of-the-box configuration `scripts/llm_cost.py` reports every
model as `unpriced` and labels the total a floor. Tokens are the ground truth and are
always recorded, so adding a rate — a single line in `_PRICES` — prices those calls
**retroactively, across every trace already written**. That is the whole reason cost is
not frozen into the record.

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
- **Unknown model ⇒ unpriced, never an error and never a guess.** Token counts are
  always stored regardless — they are the ground truth from which cost is derived.
  Unpriced is not zero, and a total containing unpriced calls is reported as a floor.
- **Read-time pricing is intentional.** Cost is a pure function of the served `model`
  and `usage`, both already in the record, so writing it in adds nothing and freezes a
  rate that may have been wrong or absent. Applying the table on read means a corrected
  or newly added rate reprices *all* history, not just future calls.

## Costing traces

```bash
uv run python scripts/llm_cost.py                      # today, per model
uv run python scripts/llm_cost.py --date 2026-07-30
uv run python scripts/llm_cost.py --interaction <uuid> # one chat question
```

The script sums in `Decimal` — floats do not round-trip a `Decimal` and drift when
thousands are summed — and separates unpriced models from genuinely free ones.

On GCS, pipe the objects in rather than copying them down:

```bash
gsutil cat 'gs://<bucket>/llm-traces/2026-07-30/*.jsonl' \
  | uv run python scripts/llm_cost.py --path -
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
5. After the first live call, run `uv run python scripts/llm_cost.py` and confirm the
   model is no longer reported as `unpriced` and the figure is plausible against the
   provider's usage dashboard.

## Follow-up queries (headline)

`scripts/llm_cost.py` answers the budget and per-model questions directly. For anything
it does not cover, the records are plain JSONL:

```bash
# token spend by source, for one day
cat data/pdfs/llm-traces/2026-07-30/*.jsonl \
  | jq -r '[.context.source, .model, .usage.total_tokens] | @tsv'

# the calls that failed but were still billed
cat data/pdfs/llm-traces/2026-07-30/*.jsonl \
  | jq -r 'select(.success == false) | [.context.source, .error.type] | @tsv'
```

Per-interaction and per-document cost queries are in
[LLM Observability](/observability.md).
