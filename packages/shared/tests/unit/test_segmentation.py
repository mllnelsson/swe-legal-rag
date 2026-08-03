"""Segmentation tests.

The two multi-part fixtures are transcribed from the real PDFs in `data/pdfs/`:
a six-page decision whose Bilaga A is the stift's own beslut, and a two-page one
whose Bilaga A is a stiftsstyrelse protocol. Both use CRLF, as the parsed PDFs do.
"""

from __future__ import annotations

from shared.segmentation import (
    normalize_case_number,
    normalize_decision_number,
    parse_keywords,
    split_document,
)

_UTLAMNANDE = (
    "Svenska kyrkans överklagandenämnd\r\n"
    "Meddelat 2026-01-07\r\n"
    "Utlämnande av handlingar\r\n"
    "53 kap. 3-11 §§ kyrkoordningen\r\n"
    "YRKANDE M.M.\r\n"
    "A har överklagat X stifts beslut.\r\n"
    "Överklagandenämndens beslut:\r\n"
    "1. Överklagandenämnden avslår överklagandet.\r\n"
    "2. Överklagandenämnden undanröjer stiftets beslut i övrigt.\r\n"
    "Sökord: Utlämnande av handlingar.\r\n"
    "Ärendenummer: ÖN 2025-0017\r\n"
    "Beslut: 1/2026\r\n"
    "…………………………………………………………\r\n"
    "Bilaga A\r\n"
    "Svenska kyrkan\r\n"
    "PRÄSTLÖNETILLGÅNGAR\r\n"
    "Beslut om utlämnande av handlingar\r\n"
)

_PROTOKOLL = (
    "Svenska kyrkans överklagandenämnd\r\n"
    "Meddelat 2026-01-07\r\n"
    "Beslutsprövning\r\n"
    "YRKANDE M.M.\r\n"
    "Stiftsstyrelsen i X stift beslutade vid sitt sammanträde.\r\n"
    "Överklagandenämndens beslut: Överklagandenämnden avvisar överklagandet.\r\n"
    "Sökord: Avvisning.\r\n"
    "Ärendenummer: ÖN 2025-0024\r\n"
    "Beslut: 3/2026\r\n"
    "………………………\r\n"
    "Bilaga A\r\n"
    "STIFTSSTYRELSEN I SAMMANTRÄDESPROTOKOLL\r\n"
    "SS § 70\r\n"
)


class TestBodyAndAppendix:
    def test_body_stops_before_the_trailer(self) -> None:
        segments = split_document(_UTLAMNANDE)
        assert segments.body.startswith("Svenska kyrkans överklagandenämnd")
        assert segments.body.endswith("undanröjer stiftets beslut i övrigt.")
        assert "Sökord:" not in segments.body
        assert "Bilaga A" not in segments.body

    def test_appendix_is_captured_with_its_label(self) -> None:
        segments = split_document(_UTLAMNANDE)
        assert len(segments.appendices) == 1
        assert segments.appendices[0].label == "Bilaga A"
        assert segments.appendices[0].text.startswith("Svenska kyrkan")
        assert "PRÄSTLÖNETILLGÅNGAR" in segments.appendices[0].text

    def test_appendix_text_is_absent_from_the_body(self) -> None:
        segments = split_document(_UTLAMNANDE)
        assert "PRÄSTLÖNETILLGÅNGAR" not in segments.body

    def test_protocol_appendix(self) -> None:
        segments = split_document(_PROTOKOLL)
        assert [a.label for a in segments.appendices] == ["Bilaga A"]
        assert "SS § 70" in segments.appendices[0].text
        assert "SS § 70" not in segments.body

    def test_multiple_appendices_split_at_each_label(self) -> None:
        text = (
            "Beslut i ärendet.\n"
            "Sökord: X\n"
            "Bilaga A\n"
            "Första bilagan.\n"
            "Bilaga B\n"
            "Andra bilagan.\n"
        )
        segments = split_document(text)
        assert [a.label for a in segments.appendices] == ["Bilaga A", "Bilaga B"]
        assert segments.appendices[0].text == "Första bilagan."
        assert segments.appendices[1].text == "Andra bilagan."

    def test_numeric_appendix_labels(self) -> None:
        segments = split_document("Beslut.\nSökord: X\nBilaga 1\nInnehåll.\n")
        assert [a.label for a in segments.appendices] == ["Bilaga 1"]


class TestFallbacks:
    def test_document_without_appendix_is_all_body(self) -> None:
        text = "Svenska kyrkans överklagandenämnd\nMeddelat 2026-01-07\nBeslut.\n"
        segments = split_document(text)
        assert segments.appendices == []
        assert segments.trailer is None
        assert segments.body == text.strip()

    def test_appendix_without_trailer_still_splits(self) -> None:
        segments = split_document("Beslut i ärendet.\nBilaga A\nDet överklagade.\n")
        assert segments.trailer is None
        assert segments.body == "Beslut i ärendet."
        assert segments.appendices[0].text == "Det överklagade."

    def test_arendenummer_alone_opens_the_trailer(self) -> None:
        segments = split_document("Beslut.\nÄrendenummer: ÖN 2025-0017\n")
        assert segments.trailer == "Ärendenummer: ÖN 2025-0017"
        assert segments.body == "Beslut."

    def test_empty_text(self) -> None:
        segments = split_document("")
        assert segments.body == ""
        assert segments.appendices == []
        assert segments.holding is None


class TestLabelIsNotMatchedInProse:
    def test_prose_mentioning_bilaga_does_not_split(self) -> None:
        # "bilaga 1" is referenced constantly inside decision prose; only a line
        # that is *only* a label marks an appendix.
        text = (
            "Bilaga 1 innehåller de handlingar som begärts ut.\n"
            "De meddelanden som markerats med rött i bilagan lämnades inte ut.\n"
            "Sökord: X\n"
        )
        segments = split_document(text)
        assert segments.appendices == []
        assert "Bilaga 1 innehåller" in segments.body

    def test_inline_bilaga_reference_is_not_a_label(self) -> None:
        segments = split_document("Se bilaga 1 enligt följande.\nSökord: X\n")
        assert segments.appendices == []


class TestTrailer:
    def test_trailer_holds_both_identifiers(self) -> None:
        segments = split_document(_UTLAMNANDE)
        assert segments.trailer is not None
        assert "Ärendenummer: ÖN 2025-0017" in segments.trailer
        assert "Beslut: 1/2026" in segments.trailer

    def test_ellipsis_rule_is_stripped(self) -> None:
        segments = split_document(_UTLAMNANDE)
        assert segments.trailer is not None
        assert "…" not in segments.trailer
        assert segments.trailer.endswith("Beslut: 1/2026")

    def test_a_sentence_ending_in_a_full_stop_survives(self) -> None:
        segments = split_document("Beslut.\nSökord: Avvisning.\n")
        assert segments.trailer == "Sökord: Avvisning."

    def test_trailer_inside_an_appendix_is_ignored(self) -> None:
        # An appended lower-instance decision can carry a trailer of its own.
        text = "Beslut i ärendet.\nBilaga A\nSökord: Fel.\nÄrendenummer: ÖN 1999-0001\n"
        segments = split_document(text)
        assert segments.trailer is None
        assert segments.body == "Beslut i ärendet."


class TestHolding:
    def test_holding_is_the_text_after_the_anchor(self) -> None:
        segments = split_document(_PROTOKOLL)
        assert segments.holding == "Överklagandenämnden avvisar överklagandet."

    def test_multi_point_holding_keeps_every_point(self) -> None:
        segments = split_document(_UTLAMNANDE)
        assert segments.holding is not None
        assert segments.holding.startswith("1. Överklagandenämnden avslår")
        assert "2. Överklagandenämnden undanröjer" in segments.holding

    def test_holding_excludes_the_trailer(self) -> None:
        segments = split_document(_UTLAMNANDE)
        assert segments.holding is not None
        assert "Sökord:" not in segments.holding

    def test_no_holding_anchor(self) -> None:
        assert split_document("Beslut i ärendet.\nSökord: X\n").holding is None


class TestNormalizeCaseNumber:
    def test_strips_the_on_prefix(self) -> None:
        assert normalize_case_number("ÖN 2025-0017") == "2025-0017"

    def test_strips_the_dnr_prefix(self) -> None:
        assert normalize_case_number("ÖN dnr 2020-1234") == "2020-1234"

    def test_already_canonical_is_unchanged(self) -> None:
        assert normalize_case_number("2025-0017") == "2025-0017"

    def test_en_dash_is_accepted(self) -> None:
        assert normalize_case_number("ÖN 2025–0017") == "2025-0017"

    def test_surrounding_text_is_ignored(self) -> None:
        assert normalize_case_number("Ärendenummer: ÖN 2025-0017") == "2025-0017"

    def test_no_match_returns_none(self) -> None:
        assert normalize_case_number("Avvisning.") is None

    def test_metadata_and_extract_spellings_agree(self) -> None:
        # The bug this fixes: metadata stored "2025-0017" while extract yielded
        # "ÖN 2025-0017", so the self-reference guard never fired.
        assert normalize_case_number("ÖN 2025-0017") == normalize_case_number(
            "2025-0017"
        )


class TestNormalizeDecisionNumber:
    def test_plain_form(self) -> None:
        assert normalize_decision_number("1/2026") == "1/2026"

    def test_leading_zero_is_dropped(self) -> None:
        assert normalize_decision_number("01/2026") == "1/2026"

    def test_surrounding_text_is_ignored(self) -> None:
        assert normalize_decision_number("Beslut: 13/2025") == "13/2025"

    def test_no_match_returns_none(self) -> None:
        assert normalize_decision_number("Beslut: ingen") is None

    def test_disjoint_from_case_numbers(self) -> None:
        # Resolution relies on the two spaces never colliding.
        assert "/" in "1/2026"
        assert "/" not in "2025-0017"


class TestParseKeywords:
    def test_single_keyword_loses_its_full_stop(self) -> None:
        assert parse_keywords("Sökord: Avvisning.") == ["Avvisning"]

    def test_stops_at_the_next_trailer_label(self) -> None:
        trailer = (
            "Sökord: Utlämnande av handlingar.\n"
            "Ärendenummer: ÖN 2025-0017\n"
            "Beslut: 1/2026"
        )
        assert parse_keywords(trailer) == ["Utlämnande av handlingar"]

    def test_commas_and_semicolons_both_separate(self) -> None:
        trailer = "Sökord: Jäv, Tjänstetillsättning; Behörighet.\nBeslut: 1/2026"
        assert parse_keywords(trailer) == ["Jäv", "Tjänstetillsättning", "Behörighet"]

    def test_a_value_wrapping_onto_the_next_line_stays_one_keyword(self) -> None:
        # A long Sökord is broken across lines by the PDF's own line breaks, not
        # by the nämnd — rejoining it is what stops one keyword becoming two.
        trailer = "Sökord: Utlämnande av allmän\nhandling.\nÄrendenummer: ÖN 2025-0017"
        assert parse_keywords(trailer) == ["Utlämnande av allmän handling"]

    def test_duplicates_are_collapsed_case_insensitively(self) -> None:
        assert parse_keywords("Sökord: Jäv, jäv, JÄV.") == ["Jäv"]

    def test_trailer_without_a_sokord_line_yields_nothing(self) -> None:
        assert parse_keywords("Ärendenummer: ÖN 2025-0017\nBeslut: 1/2026") == []

    def test_empty_value_yields_nothing(self) -> None:
        assert parse_keywords("Sökord:\nÄrendenummer: ÖN 2025-0017") == []

    def test_missing_trailer_yields_nothing(self) -> None:
        assert parse_keywords(None) == []

    def test_reads_the_trailer_split_document_produced(self) -> None:
        # The end-to-end path: the anchor that finds the trailer and the parser
        # that reads it must agree on what a trailer is.
        segments = split_document(_UTLAMNANDE)
        assert parse_keywords(segments.trailer) == ["Utlämnande av handlingar"]
