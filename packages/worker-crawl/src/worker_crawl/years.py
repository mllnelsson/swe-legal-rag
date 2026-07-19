"""Parsing of the CRAWL_YEARS / --years selector.

Pure: no I/O and no knowledge of tag ids. `today` is injected rather than read from the
clock so "current" is testable.
"""

import re
from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict

from worker_crawl.errors import YearSpecError

CURRENT_SPEC: Final = "current"
ALL_SPEC: Final = "all"

# Sanity bounds only. Whether a tag actually exists for a requested year is decided later,
# against the live tag index -- this just rejects obvious typos like "20199".
MIN_PLAUSIBLE_YEAR: Final = 1900
MAX_PLAUSIBLE_YEAR: Final = 2200

_YEAR = r"\d{4}"
_RANGE_PATTERN: Final = re.compile(rf"^(?P<start>{_YEAR})\s*-\s*(?P<end>{_YEAR})$")
_SINGLE_PATTERN: Final = re.compile(rf"^{_YEAR}$")


class YearSelection(BaseModel):
    """Which decision years to crawl.

    `all_years` is not the same as listing every known year: it additionally pulls the
    year-less "Överklagandenämndens beslut" tag, whose documents belong to no single year
    and must never appear in a routine current-year run.
    """

    model_config = ConfigDict(frozen=True)

    all_years: bool = False
    years: tuple[int, ...] = ()


def resolve_years(spec: str, today: date) -> YearSelection:
    """Parse a year selector.

    Accepts `current`, `all`, `2019`, `2019-2021`, or a comma-separated mix such as
    `2019-2021,2024`.
    """
    normalised = spec.strip().lower()
    if not normalised:
        raise YearSpecError("Year selector is empty; use 'current', 'all' or a year.")
    if normalised == CURRENT_SPEC:
        return YearSelection(years=(today.year,))
    if normalised == ALL_SPEC:
        return YearSelection(all_years=True)

    years: set[int] = set()
    for part in normalised.split(","):
        years.update(_parse_part(part.strip(), spec))
    return YearSelection(years=tuple(sorted(years)))


def _parse_part(part: str, original_spec: str) -> set[int]:
    if _SINGLE_PATTERN.match(part):
        return {_validated_year(int(part), original_spec)}

    match = _RANGE_PATTERN.match(part)
    if match is None:
        raise YearSpecError(
            f"Cannot parse {part!r} in year selector {original_spec!r}. "
            f"Expected '{CURRENT_SPEC}', '{ALL_SPEC}', '2019', '2019-2021', "
            f"or a comma-separated mix."
        )

    start = _validated_year(int(match.group("start")), original_spec)
    end = _validated_year(int(match.group("end")), original_spec)
    if start > end:
        raise YearSpecError(
            f"Year range {part!r} runs backwards: {start} is later than {end}."
        )
    return set(range(start, end + 1))


def _validated_year(year: int, original_spec: str) -> int:
    if not MIN_PLAUSIBLE_YEAR <= year <= MAX_PLAUSIBLE_YEAR:
        raise YearSpecError(
            f"Year {year} in selector {original_spec!r} is outside the plausible range "
            f"{MIN_PLAUSIBLE_YEAR}-{MAX_PLAUSIBLE_YEAR}."
        )
    return year
