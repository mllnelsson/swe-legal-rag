"""Tag index tests built on the real tag data observed on svenskakyrkan.se.

The fixture below is a verbatim snapshot of the live `/odata/tags` response for the
decision prefix, so the three quirks it encodes stay covered: a year with two tag ids
(2013), non-chronological ids (2017 > 2019), and inconsistent casing (2023).
"""

import pytest

from worker_crawl.errors import UnknownYearError
from worker_crawl.tags import (
    DecisionTag,
    TagIndex,
    parse_tag_index,
    select_tag_ids,
)
from worker_crawl.years import YearSelection

LIVE_TAGS = [
    DecisionTag(database_id=760868, name="Överklagandenämndens beslut 2000"),
    DecisionTag(database_id=760879, name="Överklagandenämndens beslut 2011"),
    # No year in the name: 125 documents belonging to no single year.
    DecisionTag(database_id=760887, name="Överklagandenämndens beslut"),
    DecisionTag(database_id=855857, name="Överklagandenämndens beslut 2012"),
    # 2013 exists twice; the first tag is empty upstream but must still be selected.
    DecisionTag(database_id=100007427, name="Överklagandenämndens beslut 2013"),
    DecisionTag(database_id=100007428, name="Överklagandenämndens beslut 2013"),
    # Ids are not chronological: 2017's id is higher than 2019's.
    DecisionTag(database_id=100064819, name="Överklagandenämndens beslut 2019"),
    DecisionTag(database_id=100065189, name="Överklagandenämndens beslut 2017"),
    # Lowercase leading 'ö' upstream.
    DecisionTag(database_id=100092236, name="överklagandenämndens beslut 2023"),
    DecisionTag(database_id=100104828, name="Överklagandenämndens beslut 2025"),
]

INDEX = parse_tag_index(LIVE_TAGS)


def test_year_with_two_tags_keeps_both_ids() -> None:
    assert INDEX.by_year[2013] == (100007427, 100007428)


def test_lowercase_tag_name_is_indexed() -> None:
    assert INDEX.by_year[2023] == (100092236,)


def test_year_less_tag_is_kept_out_of_by_year() -> None:
    assert INDEX.undated == (760887,)
    assert 0 not in INDEX.by_year
    assert all(year >= 2000 for year in INDEX.by_year)


def test_non_chronological_ids_are_looked_up_not_derived() -> None:
    assert INDEX.by_year[2017] == (100065189,)
    assert INDEX.by_year[2019] == (100064819,)
    assert INDEX.by_year[2017][0] > INDEX.by_year[2019][0]


def test_select_single_year() -> None:
    selection = select_tag_ids(INDEX, YearSelection(years=(2025,)))
    assert selection.tag_ids == (100104828,)
    assert selection.matched_years == (2025,)
    assert selection.missing_years == ()


def test_select_year_with_duplicate_tags_returns_both() -> None:
    assert select_tag_ids(INDEX, YearSelection(years=(2013,))).tag_ids == (
        100007427,
        100007428,
    )


def test_select_all_includes_the_year_less_tag() -> None:
    selection = select_tag_ids(INDEX, YearSelection(all_years=True))
    assert 760887 in selection.tag_ids
    assert len(selection.tag_ids) == len(LIVE_TAGS)


def test_current_year_selection_excludes_the_year_less_tag() -> None:
    selection = select_tag_ids(INDEX, YearSelection(years=(2025,)))
    assert 760887 not in selection.tag_ids


def test_partially_missing_years_are_reported_not_raised() -> None:
    selection = select_tag_ids(INDEX, YearSelection(years=(2025, 2099)))
    assert selection.tag_ids == (100104828,)
    assert selection.matched_years == (2025,)
    assert selection.missing_years == (2099,)


def test_entirely_missing_years_raise() -> None:
    with pytest.raises(UnknownYearError, match="2099"):
        select_tag_ids(INDEX, YearSelection(years=(2099,)))


def test_all_on_an_empty_index_raises() -> None:
    with pytest.raises(UnknownYearError):
        select_tag_ids(TagIndex(), YearSelection(all_years=True))
