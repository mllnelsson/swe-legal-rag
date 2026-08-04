"""Crawler-headline parsing tests.

The headline strings are the real shapes the OData listing returns, including
the doubled space it sometimes emits between the identifier and the title.
"""

from __future__ import annotations

import pytest

from shared.source_headline import headline_title, parse_source_headline


class TestParseSourceHeadline:
    def test_splits_identifier_from_title(self) -> None:
        parsed = parse_source_headline("Beslut 2026-23  Avskrivning")
        assert parsed is not None
        assert parsed.decision_number == "23/2026"
        assert parsed.title == "Avskrivning"

    def test_zero_padded_sequence_is_canonicalised(self) -> None:
        # The listing writes "2026-01"; the trailer writes "1/2026". Both have to
        # land in the same space for the two sources to be comparable at all.
        parsed = parse_source_headline("Beslut 2026-01 Utlämnande av handlingar")
        assert parsed is not None
        assert parsed.decision_number == "1/2026"
        assert parsed.title == "Utlämnande av handlingar"

    def test_a_multi_word_title_is_kept_whole(self) -> None:
        parsed = parse_source_headline(
            "Beslut 2026-09 Avvisad begäran om beslutsprövning"
        )
        assert parsed is not None
        assert parsed.title == "Avvisad begäran om beslutsprövning"

    @pytest.mark.parametrize(
        "headline",
        [
            None,
            "",
            "Beslut om utlämnande",
            "2026-23 Avskrivning",
            "Beslut 2026-23",
        ],
    )
    def test_anything_else_is_not_a_headline(self, headline: str | None) -> None:
        assert parse_source_headline(headline) is None


class TestHeadlineTitle:
    def test_strips_the_identifier_prefix(self) -> None:
        # The prefix duplicates `decision_number`, which every DTO carrying a
        # headline already holds as its own field.
        assert headline_title("Beslut 2026-12 Kyrkotillhörighet") == "Kyrkotillhörighet"

    def test_an_unrecognised_headline_is_returned_unchanged(self) -> None:
        # A presentation helper must never drop text it did not understand.
        assert headline_title("Beslut om utlämnande") == "Beslut om utlämnande"

    def test_missing_headline_stays_missing(self) -> None:
        assert headline_title(None) is None
