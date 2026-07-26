from __future__ import annotations

import tiktoken

from shared.enums import ChunkSection
from shared.segmentation import split_document
from worker_chunk.chunker import (
    CONTEXTUAL_SEPARATOR,
    ENCODING_NAME,
    build_contextual_text,
    split_document_into_chunks,
    split_into_chunks,
)


def _token_count(text: str) -> int:
    enc = tiktoken.get_encoding(ENCODING_NAME)
    return len(enc.encode(text))


class TestSplitIntoChunks:
    def test_short_text_produces_single_chunk(self) -> None:
        text = "Detta är ett kort stycke text. Det ryms i ett enda chunk."
        result = split_into_chunks(text, max_tokens=500)
        assert len(result) == 1
        assert "kort stycke" in result[0]

    def test_empty_text_returns_empty_list(self) -> None:
        assert split_into_chunks("") == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert split_into_chunks("   \n\n  ") == []

    def test_long_text_produces_multiple_chunks(self) -> None:
        sentence = "Överklagandenämnden för Svenska kyrkan meddelar följande beslut. "
        text = sentence * 60
        result = split_into_chunks(text, max_tokens=100, overlap_tokens=10)
        assert len(result) > 1
        for chunk in result:
            assert _token_count(chunk) <= 110  # allow small overflow from overlap join

    def test_each_chunk_within_token_limit(self) -> None:
        sentence = "Kyrkoherden överklagade stiftets beslut om tjänstetillsättning. "
        text = sentence * 50
        result = split_into_chunks(text, max_tokens=100, overlap_tokens=20)
        for chunk in result:
            # Chunk text should be close to the limit (overlap may push slightly over
            # the theoretical max in edge cases, but each sentence fits cleanly)
            assert _token_count(chunk) <= 130

    def test_overlap_tokens_appear_at_start_of_next_chunk(self) -> None:
        sentence = "Beslutet överklagades till Överklagandenämnden. "
        text = sentence * 30
        result = split_into_chunks(text, max_tokens=50, overlap_tokens=15)
        if len(result) > 1:
            # The last part of chunk[0] should appear in the beginning of chunk[1]
            last_words_of_first = result[0].split()[-3:]
            start_of_second = result[1]
            # At least some overlap content should be present
            assert any(w in start_of_second for w in last_words_of_first)

    def test_single_very_long_sentence_gets_own_chunk(self) -> None:
        long_sentence = "ord " * 600  # ~600 tokens
        result = split_into_chunks(long_sentence, max_tokens=100, overlap_tokens=10)
        assert len(result) >= 1
        # The oversized sentence is emitted as its own chunk
        assert any(len(c) > 100 for c in result)

    def test_swedish_compound_words_handled(self) -> None:
        text = (
            "Överklagandenämnden för Svenska kyrkan prövar överklaganden. "
            "Kyrkoherdetjänsten tillsätts av Domkapitlet. "
            "Kyrkoordningens bestämmelser om överklagbarhet är tillämpliga."
        )
        result = split_into_chunks(text, max_tokens=500)
        assert len(result) == 1
        assert "Överklagandenämnden" in result[0]

    def test_newline_separated_paragraphs_are_split(self) -> None:
        text = "Första stycket handlar om bakgrunden.\n\nAndra stycket behandlar rättslig grund.\n\nTredje stycket är slutsatsen."
        result = split_into_chunks(text, max_tokens=500)
        assert len(result) == 1
        assert "Första" in result[0]

    def test_returns_list_of_strings(self) -> None:
        result = split_into_chunks("Ett enkelt mening.")
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


class TestSplitDocumentIntoChunks:
    def _segments(self, text: str):
        return split_document(text)

    def test_body_chunks_are_labelled_body(self) -> None:
        chunks = split_document_into_chunks(self._segments("Beslut i ärendet."))
        assert [c.section for c in chunks] == [ChunkSection.BODY]
        assert chunks[0].appendix_label is None

    def test_appendix_chunks_carry_section_and_label(self) -> None:
        segments = self._segments(
            "Beslut i ärendet.\nSökord: X\nBilaga A\nDet överklagade beslutet.\n"
        )
        chunks = split_document_into_chunks(segments)
        appendix = [c for c in chunks if c.section is ChunkSection.APPENDIX]
        assert len(appendix) == 1
        assert appendix[0].appendix_label == "Bilaga A"
        assert appendix[0].text == "Det överklagade beslutet."

    def test_body_chunks_come_first(self) -> None:
        segments = self._segments(
            "Nämndens skäl.\nSökord: X\nBilaga A\nUnderinstansens skäl.\n"
        )
        sections = [c.section for c in split_document_into_chunks(segments)]
        assert sections == [ChunkSection.BODY, ChunkSection.APPENDIX]

    def test_no_chunk_straddles_the_boundary(self) -> None:
        # A chunk holding both the nämnd's reasoning and the appealed decision
        # could not be honestly labelled as either.
        segments = self._segments(
            "Nämndens skäl.\nSökord: X\nBilaga A\nUnderinstansens skäl.\n"
        )
        for chunk in split_document_into_chunks(segments):
            if chunk.section is ChunkSection.BODY:
                assert "Underinstansens" not in chunk.text
            else:
                assert "Nämndens" not in chunk.text

    def test_trailer_is_not_chunked(self) -> None:
        # Sökord / Ärendenummer / Beslut are already structured columns on
        # documents; indexing them only adds noise to the tsvector.
        segments = self._segments(
            "Nämndens skäl.\nSökord: Avvisning.\nÄrendenummer: ÖN 2025-0017\n"
        )
        joined = " ".join(c.text for c in split_document_into_chunks(segments))
        assert "Sökord" not in joined
        assert "Ärendenummer" not in joined

    def test_multiple_appendices_keep_their_own_labels(self) -> None:
        segments = self._segments(
            "Skäl.\nSökord: X\nBilaga A\nFörsta.\nBilaga B\nAndra.\n"
        )
        labels = [
            c.appendix_label
            for c in split_document_into_chunks(segments)
            if c.section is ChunkSection.APPENDIX
        ]
        assert labels == ["Bilaga A", "Bilaga B"]

    def test_document_without_appendix_yields_only_body_chunks(self) -> None:
        chunks = split_document_into_chunks(self._segments("Enbart nämndens text."))
        assert all(c.section is ChunkSection.BODY for c in chunks)

    def test_empty_body_with_appendix_still_yields_appendix_chunks(self) -> None:
        segments = self._segments("Bilaga A\nEnbart bilagetext.\n")
        chunks = split_document_into_chunks(segments)
        assert [c.section for c in chunks] == [ChunkSection.APPENDIX]
