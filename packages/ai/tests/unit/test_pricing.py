from __future__ import annotations

from decimal import Decimal

from llm_core import Usage

from ai._pricing import estimate_cost_usd, find_model_price

ONE_MILLION = 1_000_000


class TestFindModelPrice:
    def test_exact_prefix_matches(self) -> None:
        price = find_model_price("gemini-2.5-flash")
        assert price is not None
        assert price.input_per_1m == Decimal("0.30")

    def test_returned_suffix_is_absorbed(self) -> None:
        """Providers return dated builds; the prefix has to swallow them."""
        price = find_model_price("gemini-2.5-flash-001")
        assert price is not None
        assert price.input_per_1m == Decimal("0.30")

    def test_longest_prefix_wins(self) -> None:
        """gemini-2.5-flash-lite must not be priced as gemini-2.5-flash."""
        price = find_model_price("gemini-2.5-flash-lite-001")
        assert price is not None
        assert price.input_per_1m == Decimal("0.10")
        assert price.output_per_1m == Decimal("0.40")

    def test_matching_is_case_insensitive(self) -> None:
        assert find_model_price("Gemini-2.5-Flash") is not None

    def test_unknown_model_has_no_price(self) -> None:
        assert find_model_price("mistralai/Mistral-Small-3.2-24B-Instruct-2506") is None

    def test_no_model_has_no_price(self) -> None:
        assert find_model_price(None) is None
        assert find_model_price("") is None

    def test_shut_down_gemini_models_are_not_seeded(self) -> None:
        assert find_model_price("gemini-2.0-flash") is None
        assert find_model_price("gemini-2.0-flash-lite") is None


class TestEstimateCostUsd:
    def test_input_only_uses_the_input_rate(self) -> None:
        cost = estimate_cost_usd(
            "gemini-2.5-flash-lite", Usage(input_tokens=ONE_MILLION)
        )
        assert cost == Decimal("0.10000000")

    def test_output_only_uses_the_output_rate(self) -> None:
        cost = estimate_cost_usd(
            "gemini-2.5-flash-lite", Usage(output_tokens=ONE_MILLION)
        )
        assert cost == Decimal("0.40000000")

    def test_input_and_output_are_summed(self) -> None:
        cost = estimate_cost_usd(
            "gemini-2.5-flash",
            Usage(input_tokens=ONE_MILLION, output_tokens=ONE_MILLION),
        )
        assert cost == Decimal("2.80000000")

    def test_realistic_call_keeps_sub_cent_precision(self) -> None:
        cost = estimate_cost_usd(
            "gemini-2.5-flash-lite",
            Usage(input_tokens=1200, output_tokens=350),
        )
        assert cost == Decimal("0.00026000")

    def test_zero_tokens_costs_zero_not_null(self) -> None:
        """A genuine zero is a fact; null means unknown. They differ."""
        cost = estimate_cost_usd(
            "gemini-2.5-flash-lite", Usage(input_tokens=0, output_tokens=0)
        )
        assert cost == Decimal("0")

    def test_unpriced_model_yields_none(self) -> None:
        assert estimate_cost_usd("zai-org/GLM-5.2", Usage(input_tokens=100)) is None

    def test_missing_usage_yields_none(self) -> None:
        assert estimate_cost_usd("gemini-2.5-flash", None) is None

    def test_usage_without_token_counts_yields_none(self) -> None:
        cost = estimate_cost_usd("gemini-2.5-flash", Usage(total_tokens=42))
        assert cost is None

    def test_missing_model_yields_none(self) -> None:
        assert estimate_cost_usd(None, Usage(input_tokens=100)) is None
