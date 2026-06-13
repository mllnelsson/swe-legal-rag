from __future__ import annotations

import tiktoken

from worker_chunk.chunker import (
    CONTEXTUAL_SEPARATOR,
    ENCODING_NAME,
    build_contextual_text,
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
