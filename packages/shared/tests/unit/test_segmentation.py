"""Segmentation tests.

The two multi-part fixtures are transcribed from the real PDFs in `data/pdfs/`:
a six-page decision whose Bilaga A is the stift's own beslut, and a two-page one
whose Bilaga A is a stiftsstyrelse protocol. Both use CRLF, as the parsed PDFs do.
"""

from __future__ import annotations

import pytest

from shared.segmentation import (
    SegmentationGap,
    TrailerField,
    find_segmentation_gaps,
    normalize_case_number,
    normalize_cited_decision_number,
    normalize_decision_number,
    parse_keywords,
    parse_trailer_fields,
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

    def test_upper_case_label_splits_the_document(self) -> None:
        # The spelling 22 of the 25 corpus decisions actually use. Matching only
        # "Bilaga" left their appendices unsplit, and — with no label to bound it —
        # the trailer swallowed the appended decision whole, so 43 % of the corpus
        # was neither chunked nor entity-scanned.
        segments = split_document(_UTLAMNANDE.replace("Bilaga A", "BILAGA A"))
        assert [a.label for a in segments.appendices] == ["Bilaga A"]
        assert "PRÄSTLÖNETILLGÅNGAR" not in segments.body
        assert "PRÄSTLÖNETILLGÅNGAR" not in (segments.trailer or "")

    def test_both_spellings_yield_the_same_canonical_label(self) -> None:
        # `chunks.appendix_label` joins on this string, so one spelling has to win
        # regardless of how the source PDF happened to write it.
        upper = split_document(_UTLAMNANDE.replace("Bilaga A", "BILAGA A"))
        title = split_document(_UTLAMNANDE)
        assert upper.appendices[0].label == title.appendices[0].label == "Bilaga A"

    def test_lower_case_identifier_is_not_a_label(self) -> None:
        # Only the word is case-insensitive. Widening the identifier too would let
        # a sentence fragment left alone on a line masquerade as an appendix.
        segments = split_document("Beslut.\nSökord: X\nbilaga a\nInnehåll.\n")
        assert segments.appendices == []


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

    def test_the_earliest_label_opens_the_trailer(self) -> None:
        # One corpus decision puts Sökord last. Anchoring on the first pattern
        # tried rather than the earliest match cut the trailer at its final line
        # and left the document's own identifiers in `body`, where they defeat the
        # self-citation guard.
        text = (
            "Beslut i ärendet.\r\n"
            "Ärendenummer: ÖN 2026-0014\r\n"
            "Beslut: 23/2026\r\n"
            "Sökord: Avskrivning\r\n"
        )
        segments = split_document(text)
        assert segments.body == "Beslut i ärendet."
        assert segments.trailer is not None
        assert "Ärendenummer: ÖN 2026-0014" in segments.trailer
        assert "Beslut: 23/2026" in segments.trailer


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

    def test_the_anchor_written_as_a_bare_heading(self) -> None:
        # Two corpus decisions head the holding without a colon. Missing it cost
        # them their holding, and with it `decision_outcome` and every PRIMARY
        # entity — the whole point of segmenting.
        text = (
            "YRKANDE M.M.\n"
            "A har överklagat.\n"
            "Överklagandenämndens beslut\n"
            "Överklagandenämnden avslår överklagandet.\n"
            "Sökord: Avvisning.\n"
        )
        assert (
            split_document(text).holding == "Överklagandenämnden avslår överklagandet."
        )

    def test_the_anchor_is_not_matched_in_prose(self) -> None:
        # "Överklagandenämndens beslut 8/01" names a different decision. Reading it
        # as this one's holding would attribute another ruling's words to it.
        text = (
            "Jfr Överklagandenämndens beslut 8/01 och 2/04.\n"
            "Nämnden avslår överklagandet.\n"
        )
        assert split_document(text).holding is None


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

    @pytest.mark.parametrize(
        "text",
        [
            "Meddelat 2026-04-08",
            "beslut den 2026-04-08",
            "2025-10-07",
        ],
    )
    def test_a_date_is_not_an_arendenummer(self, text: str) -> None:
        # The body fallback runs this over free prose, where "Meddelat 2026-04-08"
        # would otherwise read as case 4 of 2026 — and once the sequence is padded
        # that becomes a plausible-looking "2026-0004" rather than an obvious wrong.
        assert normalize_case_number(text) is None

    def test_a_mandate_period_is_not_an_arendenummer(self) -> None:
        assert normalize_case_number("mandatperioden 2026-2029") is None

    def test_a_short_sequence_is_zero_padded(self) -> None:
        # One corpus decision writes "ÖN 2026-04" while its 24 siblings write
        # "YYYY-NNNN". Stored unpadded, a citation written the long way could
        # never resolve to it.
        assert normalize_case_number("Ärendenummer: ÖN 2026-04") == "2026-0004"

    def test_both_spellings_reach_the_same_canonical_form(self) -> None:
        assert normalize_case_number("ÖN 2026-04") == normalize_case_number(
            "ÖN 2026-0004"
        )

    def test_a_four_digit_sequence_is_still_an_arendenummer(self) -> None:
        # Only a sequence that is itself a year of this era is rejected; 1234 is a
        # legitimate ärendenummer sequence.
        assert normalize_case_number("ÖN 2020-1234") == "2020-1234"

    def test_metadata_and_extract_spellings_agree(self) -> None:
        # The bug this fixes: metadata stored "2025-0017" while extract yielded
        # "ÖN 2025-0017", so the self-reference guard never fired.
        assert normalize_case_number("ÖN 2025-0017") == normalize_case_number(
            "2025-0017"
        )

    def test_the_slash_spelling_is_the_same_identifier(self) -> None:
        # The registry wrote "ÖN 2021/2" through 2020 and 2021. Not accepting it
        # left 41 decisions with no ärendenummer at all and sent 58 documents to
        # the LLM fallback for a field their own trailer states.
        assert normalize_case_number("Ärendenummer: ÖN 2021/2") == "2021-0002"

    def test_both_separators_reach_the_same_canonical_form(self) -> None:
        # Decision 30/2020 writes "ÖN 2020-36"; 1/2021 — the final decision in the
        # same matter — writes "ÖN 2020/36" for the same ärende.
        assert normalize_case_number("ÖN 2020/36") == normalize_case_number(
            "ÖN 2020-36"
        )

    def test_a_stray_leading_digit_is_scanned_past(self) -> None:
        # Two corpus trailers read "ÖN 32020/33" and "ÖN 32020/35". The recovered
        # numbers are the ones the surrounding decisions confirm.
        assert normalize_case_number("Ärendenummer: ÖN 32020/33") == "2020-0033"

    def test_a_beslutsnummer_is_not_an_arendenummer(self) -> None:
        # The two spaces must stay disjoint now that both can be written with a
        # slash: an ärendenummer leads with the year, a beslutsnummer ends with it.
        assert normalize_case_number("Beslut: 5/2021") is None


class TestNormalizeDecisionNumber:
    def test_plain_form(self) -> None:
        assert normalize_decision_number("1/2026") == "1/2026"

    def test_leading_zero_is_dropped(self) -> None:
        assert normalize_decision_number("01/2026") == "1/2026"

    def test_surrounding_text_is_ignored(self) -> None:
        assert normalize_decision_number("Beslut: 13/2025") == "13/2025"

    def test_no_match_returns_none(self) -> None:
        assert normalize_decision_number("Beslut: ingen") is None

    def test_hyphen_form_is_accepted(self) -> None:
        # One corpus decision writes its beslutsnummer with a hyphen. Requiring a
        # slash left that document with no decision number at all.
        assert normalize_decision_number("Beslut: 23-2026") == "23/2026"

    @pytest.mark.parametrize(
        "text",
        [
            "Ärendenummer: ÖN 2026-0014",
            "Meddelat 2026-01-07",
            "mandatperioden 2026-2029",
        ],
    )
    def test_the_hyphen_form_does_not_swallow_other_identifiers(
        self, text: str
    ) -> None:
        assert normalize_decision_number(text) is None

    def test_disjoint_from_case_numbers(self) -> None:
        # Resolution relies on the two spaces never colliding. The separator no
        # longer says which is which — both are written with a slash somewhere in
        # the corpus — so what keeps them apart is which side carries the year.
        assert normalize_decision_number("5/2021") == "5/2021"
        assert normalize_case_number("5/2021") is None
        assert normalize_case_number("ÖN 2021/5") == "2021-0005"
        assert normalize_decision_number("ÖN 2021/5") is None


class TestNormalizeCitedDecisionNumber:
    """The year-first spelling, which only a caller reading a citation may apply."""

    def test_the_plain_form_still_wins(self) -> None:
        assert normalize_cited_decision_number("nämndens beslut 13/2025") == "13/2025"

    def test_the_year_first_form_is_the_same_beslutsnummer(self) -> None:
        # 25/2026 cites "beslut 2010/06 och 2022/15" for a begäran om utlämnande;
        # decision 15/2022 is "Utlämnande av handling".
        assert normalize_cited_decision_number("beslut 2022/15") == "15/2022"
        assert normalize_cited_decision_number("beslut 2010/06") == "6/2010"

    def test_the_headline_spelling_is_accepted(self) -> None:
        # The listing writes "Beslut 2020-24" for decision 24/2020, and the PDF's
        # own title line writes "Beslut 2020/24".
        assert normalize_cited_decision_number("Beslut 2020-24") == "24/2020"

    def test_a_date_is_not_a_citation(self) -> None:
        # "Domkapitlets beslut 2025-08-19 § 104" and a line-wrapped "2024-10-\n14".
        assert normalize_cited_decision_number("beslut 2025-08-19") is None
        assert normalize_cited_decision_number("beslutet 2024-10-\n14") is None

    def test_a_mandate_period_is_not_a_citation(self) -> None:
        assert normalize_cited_decision_number("mandatperioden 2026-2029") is None

    def test_the_strict_function_is_left_alone(self) -> None:
        # Widening `normalize_decision_number` itself would make an ärendenummer
        # read as a beslutsnummer everywhere the trailer is parsed.
        assert normalize_decision_number("2022/15") is None
        assert normalize_case_number("ÖN 2022/15") == "2022-0015"


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

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Kyrkobyggnad. Kyrkorum.", ["Kyrkobyggnad", "Kyrkorum"]),
            (
                "Beslutsprövning. Kyrkofullmäktige. Protokollföring",
                ["Beslutsprövning", "Kyrkofullmäktige", "Protokollföring"],
            ),
            ("Avvisning", ["Avvisning"]),
        ],
    )
    def test_a_full_stop_separates_keywords(
        self, value: str, expected: list[str]
    ) -> None:
        # The separator every Sökord line in the corpus actually uses. Splitting on
        # commas alone returned "Kyrkobyggnad. Kyrkorum" as a single keyword.
        assert parse_keywords(f"Sökord: {value}") == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Omprövning. Utlämnande av handling.", "Utlämnande av handling"),
            ("Omprövning. Upplåtelse av kyrka.", "Upplåtelse av kyrka"),
            ("Saklig prövning.", "Saklig prövning"),
        ],
    )
    def test_whitespace_never_separates_keywords(
        self, value: str, expected: str
    ) -> None:
        # Multi-word keywords are common in the corpus; only punctuation splits.
        assert parse_keywords(f"Sökord: {value}")[-1] == expected

    def test_an_abbreviation_is_neither_split_nor_truncated(self) -> None:
        # The stop in "m.m." is part of the keyword. The separator lookahead is
        # what stops it splitting; stripping a single trailing stop rather than a
        # run of them is what stops it becoming "Avskrivning m.m".
        assert parse_keywords("Sökord: Avskrivning m.m.") == ["Avskrivning m.m."]

    def test_a_rule_line_is_not_a_keyword(self) -> None:
        # The corpus draws the rule between trailer and appendix with dashes as
        # well as ellipses; an unrecognised rule line was folded into the value.
        trailer = "Sökord: Avskrivning\n--------------------\n"
        assert parse_keywords(trailer) == ["Avskrivning"]

    def test_a_trailer_listing_sokord_last_still_yields_one_keyword(self) -> None:
        # The ordering that made the old lookahead run to end-of-document, turning
        # the whole appended decision into four "keywords".
        trailer = "Ärendenummer: ÖN 2026-0014\nBeslut: 23-2026\nSökord: Avskrivning\n"
        assert parse_keywords(trailer) == ["Avskrivning"]

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


class TestFindSegmentationGaps:
    def test_a_well_formed_decision_has_no_gaps(self) -> None:
        assert find_segmentation_gaps(split_document(_UTLAMNANDE)) == []

    def test_a_bare_paragraph_is_missing_everything(self) -> None:
        gaps = find_segmentation_gaps(split_document("Ett stycke text."))
        assert set(gaps) == set(SegmentationGap)

    def test_a_missing_appendix_is_reported_on_its_own(self) -> None:
        # The shape the case-sensitive label bug produced for 22 of 25 documents,
        # and which nothing anywhere reported at the time.
        text = _UTLAMNANDE.replace("Bilaga A\r\n", "")
        assert find_segmentation_gaps(split_document(text)) == [
            SegmentationGap.NO_APPENDIX
        ]


class TestParseTrailerFields:
    def test_reads_every_label(self) -> None:
        segments = split_document(_UTLAMNANDE)
        assert parse_trailer_fields(segments.trailer) == {
            TrailerField.KEYWORDS: "Utlämnande av handlingar.",
            TrailerField.CASE_NUMBER: "ÖN 2025-0017",
            TrailerField.DECISION_NUMBER: "1/2026",
        }

    def test_field_order_does_not_matter(self) -> None:
        reordered = "Ärendenummer: ÖN 2026-0014\nBeslut: 23-2026\nSökord: Avskrivning"
        assert parse_trailer_fields(reordered) == {
            TrailerField.CASE_NUMBER: "ÖN 2026-0014",
            TrailerField.DECISION_NUMBER: "23-2026",
            TrailerField.KEYWORDS: "Avskrivning",
        }

    def test_a_wrapped_value_is_folded_back_onto_its_field(self) -> None:
        trailer = "Sökord: Utlämnande av allmän\nhandling.\nBeslut: 1/2026"
        fields = parse_trailer_fields(trailer)
        assert fields[TrailerField.KEYWORDS] == "Utlämnande av allmän handling."
        assert fields[TrailerField.DECISION_NUMBER] == "1/2026"

    def test_a_rule_line_ends_a_value(self) -> None:
        trailer = "Sökord: Avskrivning\n--------\nnågot annat"
        assert parse_trailer_fields(trailer) == {TrailerField.KEYWORDS: "Avskrivning"}

    def test_missing_trailer_is_empty(self) -> None:
        assert parse_trailer_fields(None) == {}

    def test_trailer_without_labels_is_empty(self) -> None:
        assert parse_trailer_fields("Beslut i ärendet.") == {}
