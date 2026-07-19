from datetime import date

import pytest

from worker_crawl.errors import YearSpecError
from worker_crawl.years import YearSelection, resolve_years

TODAY = date(2026, 7, 19)


def test_current_uses_injected_today() -> None:
    assert resolve_years("current", TODAY) == YearSelection(years=(2026,))


def test_all_sets_all_years_flag_without_listing_years() -> None:
    selection = resolve_years("all", TODAY)
    assert selection == YearSelection(all_years=True)
    assert selection.years == ()


def test_single_year() -> None:
    assert resolve_years("2019", TODAY) == YearSelection(years=(2019,))


def test_inclusive_range() -> None:
    assert resolve_years("2019-2021", TODAY) == YearSelection(years=(2019, 2020, 2021))


def test_comma_separated_list_is_sorted_and_deduplicated() -> None:
    assert resolve_years("2024,2019,2024", TODAY) == YearSelection(years=(2019, 2024))


def test_mixed_ranges_and_singles() -> None:
    assert resolve_years("2019-2021,2024", TODAY) == YearSelection(
        years=(2019, 2020, 2021, 2024)
    )


@pytest.mark.parametrize("spec", ["CURRENT", " All ", "2019 - 2021"])
def test_specs_are_case_and_whitespace_insensitive(spec: str) -> None:
    resolve_years(spec, TODAY)


@pytest.mark.parametrize(
    "spec",
    ["", "   ", "twenty", "20199", "2019-", "-2019", "2019--2021", "2019,,2020"],
)
def test_malformed_specs_are_rejected(spec: str) -> None:
    with pytest.raises(YearSpecError):
        resolve_years(spec, TODAY)


def test_backwards_range_is_rejected() -> None:
    with pytest.raises(YearSpecError, match="backwards"):
        resolve_years("2021-2019", TODAY)


def test_implausible_year_is_rejected() -> None:
    with pytest.raises(YearSpecError, match="plausible"):
        resolve_years("1499", TODAY)
