from __future__ import annotations

from shared.enums import ChunkSection
from shared.segmentation import split_document
from worker_chunk.budget import ChunkBudget
from worker_chunk.chunker import (
    CONTEXTUAL_SEPARATOR,
    build_contextual_text,
    split_document_into_chunks,
    split_into_chunks,
    truncate_summary,
)


def _count_words(text: str) -> int:
    """The ruler these tests budget in.

    Words, not the embedding model's tokens: the chunker takes its counter as a
    parameter precisely so the unit suite never has to load a tokenizer — and so
    that the numbers in each test are readable from the text they measure.
    """
    return len(text.split())


_BUDGET = ChunkBudget(max_tokens=50, overlap_tokens=5, summary_reserve_tokens=20)


class TestSplitIntoChunks:
    def test_short_text_produces_single_chunk(self) -> None:
        text = "Detta är ett kort stycke text. Det ryms i ett enda chunk."
        result = split_into_chunks(
            text, count_tokens=_count_words, max_tokens=500, overlap_tokens=50
        )
        assert len(result) == 1
        assert "kort stycke" in result[0]

    def test_empty_text_returns_empty_list(self) -> None:
        assert (
            split_into_chunks(
                "", count_tokens=_count_words, max_tokens=500, overlap_tokens=50
            )
            == []
        )

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert (
            split_into_chunks(
                "   \n\n  ",
                count_tokens=_count_words,
                max_tokens=500,
                overlap_tokens=50,
            )
            == []
        )

    def test_long_text_produces_multiple_chunks(self) -> None:
        sentence = "Överklagandenämnden för Svenska kyrkan meddelar följande beslut. "
        text = sentence * 60
        max_tokens, overlap_tokens = 100, 10
        result = split_into_chunks(
            text,
            count_tokens=_count_words,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        assert len(result) > 1
        for chunk in result:
            # The repeated overlap is the only thing that can push a chunk past
            # the budget, so that is the bound — not an unexplained allowance.
            assert _count_words(chunk) <= max_tokens + overlap_tokens

    def test_each_chunk_within_token_limit(self) -> None:
        sentence = "Kyrkoherden överklagade stiftets beslut om tjänstetillsättning. "
        text = sentence * 50
        max_tokens, overlap_tokens = 100, 20
        result = split_into_chunks(
            text,
            count_tokens=_count_words,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        for chunk in result:
            assert _count_words(chunk) <= max_tokens + overlap_tokens

    def test_overlap_tokens_appear_at_start_of_next_chunk(self) -> None:
        sentence = "Beslutet överklagades till Överklagandenämnden. "
        text = sentence * 30
        result = split_into_chunks(
            text, count_tokens=_count_words, max_tokens=50, overlap_tokens=15
        )
        if len(result) > 1:
            # The last part of chunk[0] should appear in the beginning of chunk[1]
            last_words_of_first = result[0].split()[-3:]
            start_of_second = result[1]
            # At least some overlap content should be present
            assert any(w in start_of_second for w in last_words_of_first)

    def test_single_very_long_sentence_gets_own_chunk(self) -> None:
        # A sentence larger than the whole budget is emitted intact rather than
        # cut mid-thought. That chunk overruns the embedding window and will be
        # truncated by the model; the chunk service warns about exactly this.
        long_sentence = "ord " * 600
        max_tokens = 100
        result = split_into_chunks(
            long_sentence,
            count_tokens=_count_words,
            max_tokens=max_tokens,
            overlap_tokens=10,
        )
        assert len(result) >= 1
        assert any(_count_words(chunk) > max_tokens for chunk in result)

    def test_swedish_compound_words_handled(self) -> None:
        text = (
            "Överklagandenämnden för Svenska kyrkan prövar överklaganden. "
            "Kyrkoherdetjänsten tillsätts av Domkapitlet. "
            "Kyrkoordningens bestämmelser om överklagbarhet är tillämpliga."
        )
        result = split_into_chunks(
            text, count_tokens=_count_words, max_tokens=500, overlap_tokens=50
        )
        assert len(result) == 1
        assert "Överklagandenämnden" in result[0]

    def test_newline_separated_paragraphs_are_split(self) -> None:
        text = "Första stycket handlar om bakgrunden.\n\nAndra stycket behandlar rättslig grund.\n\nTredje stycket är slutsatsen."
        result = split_into_chunks(
            text, count_tokens=_count_words, max_tokens=500, overlap_tokens=50
        )
        assert len(result) == 1
        assert "Första" in result[0]

    def test_returns_list_of_strings(self) -> None:
        result = split_into_chunks(
            "Ett enkelt mening.",
            count_tokens=_count_words,
            max_tokens=500,
            overlap_tokens=50,
        )
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)


class TestBuildContextualText:
    def test_concatenates_summary_and_chunk_with_separator(self) -> None:
        summary = "Sammanfattning av beslutet."
        chunk = "Detaljerat innehåll i chunken."
        result = build_contextual_text(summary, chunk)
        assert result == f"{summary}{CONTEXTUAL_SEPARATOR}{chunk}"

    def test_summary_appears_before_separator(self) -> None:
        summary = "Sammanfattning."
        chunk = "Chunk text."
        result = build_contextual_text(summary, chunk)
        assert result.startswith(summary)

    def test_chunk_appears_after_separator(self) -> None:
        summary = "Sammanfattning."
        chunk = "Chunk text."
        result = build_contextual_text(summary, chunk)
        assert result.endswith(chunk)

    def test_empty_summary_produces_valid_output(self) -> None:
        result = build_contextual_text("", "Chunk text.")
        assert "Chunk text." in result
        assert CONTEXTUAL_SEPARATOR in result

    def test_separator_present(self) -> None:
        result = build_contextual_text("Summary.", "Chunk.")
        assert CONTEXTUAL_SEPARATOR in result


class TestTruncateSummary:
    def test_summary_within_the_reserve_is_untouched(self) -> None:
        summary = "Nämnden avslog överklagandet. Beslutet står fast."

        assert (
            truncate_summary(summary, count_tokens=_count_words, max_tokens=20)
            == summary
        )

    def test_long_summary_is_cut_to_the_reserve(self) -> None:
        summary = " ".join(f"Mening nummer {i} om beslutet." for i in range(20))

        result = truncate_summary(summary, count_tokens=_count_words, max_tokens=20)

        assert _count_words(result) <= 20
        assert summary.startswith(result)

    def test_cut_lands_on_a_sentence_boundary(self) -> None:
        summary = " ".join(f"Mening nummer {i} om beslutet." for i in range(20))

        result = truncate_summary(summary, count_tokens=_count_words, max_tokens=20)

        assert result.endswith(".")

    def test_run_on_summary_falls_back_to_whole_words(self) -> None:
        # No sentence boundary to cut on. Returning nothing here would strip the
        # context from every chunk of the document.
        summary = "ord " * 100

        result = truncate_summary(summary, count_tokens=_count_words, max_tokens=10)

        assert result
        assert _count_words(result) <= 10

    def test_empty_summary_stays_empty(self) -> None:
        assert truncate_summary("", count_tokens=_count_words, max_tokens=20) == ""

    def test_is_deterministic(self) -> None:
        summary = " ".join(f"Mening nummer {i} om beslutet." for i in range(20))

        first = truncate_summary(summary, count_tokens=_count_words, max_tokens=20)
        second = truncate_summary(summary, count_tokens=_count_words, max_tokens=20)

        assert first == second


class TestSplitDocumentIntoChunks:
    def _segments(self, text: str):
        return split_document(text)

    def _chunks(self, text: str):
        return split_document_into_chunks(
            self._segments(text), count_tokens=_count_words, budget=_BUDGET
        )

    def test_body_chunks_are_labelled_body(self) -> None:
        chunks = self._chunks("Beslut i ärendet.")
        assert [c.section for c in chunks] == [ChunkSection.BODY]
        assert chunks[0].appendix_label is None

    def test_appendix_chunks_carry_section_and_label(self) -> None:
        chunks = self._chunks(
            "Beslut i ärendet.\nSökord: X\nBilaga A\nDet överklagade beslutet.\n"
        )
        appendix = [c for c in chunks if c.section is ChunkSection.APPENDIX]
        assert len(appendix) == 1
        assert appendix[0].appendix_label == "Bilaga A"
        assert appendix[0].text == "Det överklagade beslutet."

    def test_body_chunks_come_first(self) -> None:
        sections = [
            c.section
            for c in self._chunks(
                "Nämndens skäl.\nSökord: X\nBilaga A\nUnderinstansens skäl.\n"
            )
        ]
        assert sections == [ChunkSection.BODY, ChunkSection.APPENDIX]

    def test_no_chunk_straddles_the_boundary(self) -> None:
        # A chunk holding both the nämnd's reasoning and the appealed decision
        # could not be honestly labelled as either.
        for chunk in self._chunks(
            "Nämndens skäl.\nSökord: X\nBilaga A\nUnderinstansens skäl.\n"
        ):
            if chunk.section is ChunkSection.BODY:
                assert "Underinstansens" not in chunk.text
            else:
                assert "Nämndens" not in chunk.text

    def test_trailer_is_not_chunked(self) -> None:
        # Sökord / Ärendenummer / Beslut are already structured columns on
        # documents; indexing them only adds noise to the tsvector.
        joined = " ".join(
            c.text
            for c in self._chunks(
                "Nämndens skäl.\nSökord: Avvisning.\nÄrendenummer: ÖN 2025-0017\n"
            )
        )
        assert "Sökord" not in joined
        assert "Ärendenummer" not in joined

    def test_multiple_appendices_keep_their_own_labels(self) -> None:
        labels = [
            c.appendix_label
            for c in self._chunks(
                "Skäl.\nSökord: X\nBilaga A\nFörsta.\nBilaga B\nAndra.\n"
            )
            if c.section is ChunkSection.APPENDIX
        ]
        assert labels == ["Bilaga A", "Bilaga B"]

    def test_document_without_appendix_yields_only_body_chunks(self) -> None:
        chunks = self._chunks("Enbart nämndens text.")
        assert all(c.section is ChunkSection.BODY for c in chunks)

    def test_empty_body_with_appendix_still_yields_appendix_chunks(self) -> None:
        chunks = self._chunks("Bilaga A\nEnbart bilagetext.\n")
        assert [c.section for c in chunks] == [ChunkSection.APPENDIX]
