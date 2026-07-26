import pytest

from worker_parse.parser import (
    ParseError,
    Parser,
    normalize_typographic_chars,
    parse_pdf_with_pypdfium2,
    rejoin_hyphenated_words,
)


def test_normalize_typographic_chars_replaces_dash_variants() -> None:
    text = "Ärendenummer: ÖN 2025–0008"  # en dash
    assert normalize_typographic_chars(text) == "Ärendenummer: ÖN 2025-0008"


def test_normalize_typographic_chars_replaces_smart_quotes() -> None:
    text = "‘quoted’ and “double”"
    assert normalize_typographic_chars(text) == "'quoted' and \"double\""


def test_normalize_typographic_chars_leaves_ascii_untouched() -> None:
    text = "Ärendenummer: ÖN 2023-0042"
    assert normalize_typographic_chars(text) == text


def test_parse_valid_pdf_returns_nonempty_string(minimal_pdf_bytes: bytes) -> None:
    result = parse_pdf_with_pypdfium2(minimal_pdf_bytes)
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Test Content" in result


def test_parse_invalid_bytes_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_pdf_with_pypdfium2(b"not a pdf at all")


def test_custom_function_satisfies_parser_protocol() -> None:
    def my_parser(pdf_bytes: bytes) -> str:
        return f"parsed {len(pdf_bytes)} bytes"

    parser: Parser = my_parser
    assert parser(b"hello") == "parsed 5 bytes"


# U+FFFE is a Unicode noncharacter; writing it as an escape keeps these fixtures
# readable and copy/paste-safe.
MARK = "\ufffe"


class TestRejoinHyphenatedWords:
    """pypdfium2 marks a line-break hyphen with U+FFFE and drops the newline.

    Every input below is transcribed from
    data/pdfs/documents/d5448279-86e9-4db5-ae25-019c404def1b/original.pdf.
    """

    def test_typographic_hyphen_is_dropped(self) -> None:
        text = f"den inomkyrkliga hand{MARK}lingsoffentligheten"
        assert rejoin_hyphenated_words(text) == (
            "den inomkyrkliga handlingsoffentligheten"
        )

    def test_rejoins_across_a_capitalised_stem(self) -> None:
        assert (
            rejoin_hyphenated_words(f"\u00d6ver{MARK}klagandet") == "\u00d6verklagandet"
        )

    def test_rejoins_a_compound(self) -> None:
        assert rejoin_hyphenated_words(f"advokat{MARK}firman S") == "advokatfirman S"

    def test_short_stem_keeps_its_lexical_hyphen(self) -> None:
        # "e-post" is genuinely hyphenated; the wrap merely happened to land there.
        assert rejoin_hyphenated_words(f"intern e{MARK}post") == "intern e-post"

    def test_short_stem_keeps_hyphen_when_inflected(self) -> None:
        assert rejoin_hyphenated_words(f"liksom e{MARK}posten") == "liksom e-posten"

    def test_text_without_the_mark_is_untouched(self) -> None:
        text = "Mark- och milj\u00f6\u00f6verdomstolen upph\u00e4vde detaljplanen."
        assert rejoin_hyphenated_words(text) == text

    def test_no_noncharacter_survives(self) -> None:
        assert MARK not in rejoin_hyphenated_words(f"hand{MARK}lingsoffentlighet")

    def test_composes_with_typographic_normalization(self) -> None:
        result = rejoin_hyphenated_words(
            normalize_typographic_chars(f"advokat{MARK}firman \u2013 e{MARK}post")
        )
        assert result == "advokatfirman - e-post"
