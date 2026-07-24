import pytest

from worker_parse.parser import (
    ParseError,
    Parser,
    normalize_typographic_chars,
    parse_pdf_with_pypdfium2,
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
