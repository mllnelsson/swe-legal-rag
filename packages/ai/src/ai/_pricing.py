"""Read-time cost estimation from provider token counts.

Cost is a pure function of the served model and the token counts, both of which
a trace record already carries. Nothing here runs on the write path: pricing at
read time costs nothing, and it means a rate that was wrong or missing when a
call happened can be corrected across the whole history rather than only for
future calls. Adding a rate below re-prices every trace ever written — which
matters, because the models this project runs by default are currently unpriced.

Token counts are the ground truth; this table is an interpretation of them.

See [LLM Pricing Prerequisites](/reference/llm-pricing.md) for the source of
truth, the verification rules, and the maintenance checklist. The reader that
applies this table is `scripts/llm_cost.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from llm_core import Usage

TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)

# Eight decimal places. A single cheap call costs well under a cent, and
# rounding to fewer digits would floor most of them to zero.
COST_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_1m: Decimal
    output_per_1m: Decimal


# Keyed by lowercased model-name *prefix*, matched longest-first. The model a
# provider returns carries suffixes the configured name does not (`-001`,
# preview tags), and prefix matching absorbs them.
#
# UNPRICED, and deliberately so: the Berget-hosted models this project runs by
# default — mistralai/Mistral-Small-3.2-24B-Instruct-2506,
# mistralai/Mistral-Medium-3.5-128B, zai-org/GLM-5.2, and
# intfloat/multilingual-e5-large. Their per-1M rates are not published in this
# repo, and guessing them would be worse than reporting nothing. Until they are
# added here, traces on the default configuration carry tokens and a null cost.
# Adding one is a single line; see the maintenance checklist in the reference.
_PRICES: dict[str, ModelPrice] = {
    # Gemini, verified 2026-06-13. gemini-2.0-flash and -lite shut down
    # 2026-06-01 and are intentionally absent.
    "gemini-2.5-flash-lite": ModelPrice(Decimal("0.10"), Decimal("0.40")),
    "gemini-2.5-flash": ModelPrice(Decimal("0.30"), Decimal("2.50")),
}


def find_model_price(model: str | None) -> ModelPrice | None:
    """Longest-prefix match, case-insensitively.

    Case folding is not cosmetic: Berget model ids are mixed-case, and matching
    them case-sensitively would silently yield null costs forever.
    """
    if not model:
        return None

    normalized = model.lower()
    matches = [prefix for prefix in _PRICES if normalized.startswith(prefix)]
    if not matches:
        return None
    return _PRICES[max(matches, key=len)]


def estimate_cost_usd(model: str | None, usage: Usage | None) -> Decimal | None:
    """Cost of one call, or None when it cannot be known.

    Never raises and never guesses. None means "unpriced or unreported" and is
    distinct from a genuine zero — anything summing these must treat the two
    differently or it will silently under-report spend.
    """
    if usage is None:
        return None

    price = find_model_price(model)
    if price is None:
        return None

    if usage.input_tokens is None and usage.output_tokens is None:
        return None

    input_cost = Decimal(usage.input_tokens or 0) * price.input_per_1m
    output_cost = Decimal(usage.output_tokens or 0) * price.output_per_1m
    total = (input_cost + output_cost) / TOKENS_PER_PRICE_UNIT
    return total.quantize(COST_QUANTUM)
