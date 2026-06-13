# Observability

> **Status:** design phase. Implementation is planned in ATM stories 15 (LLM trace capture & cost tracking) and 16 (end-to-end interaction tracking & pipeline health). The full design decisions (D1–D8) live in those story descriptions and will be consolidated here when story 15 is built. This document currently specifies the **LLM pricing prerequisites**, which the cost-tracking implementation (story 15, task 3) depends on.

## Why cost tracking exists

A core project goal is seeing how cheap the system can run (PRD: <$5/month LLM budget). Every LLM call is traced to a Postgres `llm_traces` row storing the full prompt/response, token counts, latency, and a write-time `estimated_cost_usd` computed from the pricing table described below.

## LLM pricing prerequisites

### Source of truth

Prices come from Google's official Gemini API pricing page: <https://ai.google.dev/gemini-api/docs/pricing>.

- Use the **paid tier, standard** rates (not batch — the pipeline makes interactive calls).
- Use the **text** input rate. The pipeline sends text only; audio/video rates, context-caching rates, and cache-storage rates are out of scope. If context caching or batch calls are ever adopted, the pricing model here must be extended first.
- Prices must be re-verified **whenever `LLM_MODEL` changes** and whenever a builder touches `ai/_pricing.py`.

### Verified prices (checked 2026-06-13)

| Model prefix | Input USD / 1M tokens | Output USD / 1M tokens | Note |
|---|---|---|---|
| `gemini-2.5-flash-lite` | 0.10 | 0.40 | Recommended default — same price point as the old 2.0-flash |
| `gemini-2.5-flash` | 0.30 | 2.50 | |
| `gemini-2.0-flash` | — | — | **Shut down 2026-06-01. Do not seed; calls fail.** |
| `gemini-2.0-flash-lite` | — | — | **Shut down 2026-06-01. Do not seed; calls fail.** |

No context-length pricing tiers apply to these models (verified on the pricing page); the table assumes a flat per-token rate. If Google introduces tiered pricing for an adopted model, `estimate_cost_usd()` must be extended — do not approximate with the base rate silently.

> **⚠ Action required before any live LLM call:** the repo's configured default is `LLM_MODEL=gemini-2.0-flash` (`packages/llm-core/src/llm_core/_config.py`, `.env.example`, `LOCAL_DEV.md`), which was shut down on 2026-06-01. A replacement must be chosen and updated in all three places before live testing. `gemini-2.5-flash-lite` matches the old model's price.

### Table semantics (binding for `ai/_pricing.py`)

- **Units:** USD per 1M tokens, input and output priced separately. Stored as `Decimal` — never float (`estimated_cost_usd` is `NUMERIC(12,8)`).
- **Keying:** model-name **prefix**, matched longest-prefix-first against the model string the API *returns* (`response.model_version`), not only the configured name. The returned string can carry suffixes (e.g. `-001`, preview tags); prefix matching absorbs them. Longest-prefix-first is required so `gemini-2.5-flash-lite` wins over `gemini-2.5-flash` for lite models.
- **Unknown model ⇒ `NULL` cost, never an error and never a guess.** Token counts are always stored regardless — they are the ground truth from which cost can be recomputed.
- **Write-time freeze is intentional:** `estimated_cost_usd` records the price in effect when the call happened. Later price changes update the table for *future* calls only; historical rows are not rewritten.

### Recomputing cost from tokens

If a price was wrong or missing, recompute from the stored tokens instead of editing history blindly:

```sql
-- e.g. backfill rows that had no pricing entry at write time
UPDATE llm_traces
SET estimated_cost_usd = (input_tokens * 0.10 + output_tokens * 0.40) / 1000000.0
WHERE model LIKE 'gemini-2.5-flash-lite%' AND estimated_cost_usd IS NULL;
```

### Maintenance checklist

When changing the model or touching pricing (do these in the same change):

1. Check the pricing page; record the date checked in the table above.
2. Add/adjust the prefix entry in `ai/_pricing.py` (Decimal, per 1M tokens, standard text rates).
3. Confirm the model has no context-length pricing tiers; if it does, extend `estimate_cost_usd()` first.
4. Update `LLM_MODEL` in `.env.example` and the LOCAL_DEV.md env listing if the default changes.
5. After the first live call, sanity-check one `llm_traces` row: `estimated_cost_usd` non-null and plausible against the Google AI Studio usage dashboard.

## Follow-up queries (headline)

```sql
-- LLM spend, last 30 days (the budget question)
SELECT sum(estimated_cost_usd) FROM llm_traces
WHERE created_at > now() - interval '30 days';

-- spend by model
SELECT model, count(*), sum(total_tokens), sum(estimated_cost_usd)
FROM llm_traces GROUP BY model ORDER BY 4 DESC NULLS LAST;
```

More queries (per-document cost, failure follow-up, interaction cost) will be documented when stories 15/16 are built.
