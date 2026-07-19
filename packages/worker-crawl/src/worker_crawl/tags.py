"""Decision-tag modelling and selection.

The OData listing is scoped by *tag*, and Överklagandenämnden publishes one tag per
decision year. This module turns the raw tag rows into a year index and picks the tag ids
for a requested `YearSelection`. Everything here is pure; fetching lives in `odata`.

Three quirks of the live tag data drive the shape of this code:

1. A year can map to **several** tag ids -- 2013 has two (one of them empty) -- so the
   index stores a tuple of ids per year, never a single id.
2. Tag ids are **not** chronological (2017 is 100065189, 2019 is 100064819), so an id can
   never be derived arithmetically from a year; it must be looked up.
3. Tag names are **inconsistently cased** ("överklagandenämndens beslut 2023" is
   lowercase), so nothing may match on name casing.

One tag, "Överklagandenämndens beslut", carries no year at all. Its documents are exposed
as `undated` and are pulled in only by an explicit `all` selection.
"""

import re
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from worker_crawl.errors import UnknownYearError
from worker_crawl.years import ALL_SPEC, YearSelection

# Tags are matched by this prefix server-side; OData's startswith is case-insensitive,
# which is what makes the lowercase 2023 tag reachable.
DECISION_TAG_PREFIX: Final = "Överklagandenämndens beslut"

# A decision-year tag is the prefix followed by a trailing four-digit year.
_TRAILING_YEAR_PATTERN: Final = re.compile(r"(\d{4})$")


class DecisionTag(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_id: int
    name: str


class TagIndex(BaseModel):
    """Decision tags grouped by the year in their name."""

    model_config = ConfigDict(frozen=True)

    by_year: dict[int, tuple[int, ...]] = {}
    undated: tuple[int, ...] = ()


class TagSelection(BaseModel):
    """Tag ids chosen for a crawl, plus what could not be matched.

    `missing_years` is returned rather than logged so this stays pure; the caller decides
    how loudly to report it.
    """

    model_config = ConfigDict(frozen=True)

    tag_ids: tuple[int, ...] = ()
    matched_years: tuple[int, ...] = ()
    missing_years: tuple[int, ...] = ()


def parse_tag_index(tags: Sequence[DecisionTag]) -> TagIndex:
    by_year: dict[int, list[int]] = {}
    undated: list[int] = []

    for tag in tags:
        year = _trailing_year(tag.name)
        if year is None:
            undated.append(tag.database_id)
        else:
            by_year.setdefault(year, []).append(tag.database_id)

    return TagIndex(
        by_year={year: tuple(ids) for year, ids in by_year.items()},
        undated=tuple(undated),
    )


def select_tag_ids(index: TagIndex, selection: YearSelection) -> TagSelection:
    if selection.all_years:
        every_year = sorted(index.by_year)
        tag_ids = [tag_id for year in every_year for tag_id in index.by_year[year]]
        tag_ids.extend(index.undated)
        return _require_tags(
            TagSelection(tag_ids=tuple(tag_ids), matched_years=tuple(every_year)),
            index,
            selection,
        )

    tag_ids = []
    matched: list[int] = []
    missing: list[int] = []
    for year in selection.years:
        ids = index.by_year.get(year)
        if ids:
            tag_ids.extend(ids)
            matched.append(year)
        else:
            missing.append(year)

    return _require_tags(
        TagSelection(
            tag_ids=tuple(tag_ids),
            matched_years=tuple(matched),
            missing_years=tuple(missing),
        ),
        index,
        selection,
    )


def _require_tags(
    result: TagSelection, index: TagIndex, selection: YearSelection
) -> TagSelection:
    """Turn "matched nothing" into a diagnosable error rather than an empty crawl.

    Without this a typo'd year would look like a clean run that found no new documents.
    """
    if result.tag_ids:
        return result

    requested = ", ".join(str(year) for year in selection.years) or ALL_SPEC
    known = sorted(index.by_year)
    available = (
        f"{known[0]}-{known[-1]}" if known else "none returned by the tags endpoint"
    )
    raise UnknownYearError(
        f"No decision tags found for {requested}. Available years: {available}."
    )


def _trailing_year(name: str) -> int | None:
    match = _TRAILING_YEAR_PATTERN.search(name.strip())
    return int(match.group(1)) if match else None
