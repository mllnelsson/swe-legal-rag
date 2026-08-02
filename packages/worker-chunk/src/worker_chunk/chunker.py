from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from ai import CountTokens
from shared.enums import ChunkSection
from shared.segmentation import DocumentSegments
from worker_chunk.budget import ChunkBudget

CONTEXTUAL_SEPARATOR = "\n\n---\n\n"


class SectionedChunk(BaseModel):
    """A chunk plus the provenance retrieval needs to keep instances apart."""

    model_config = ConfigDict(frozen=True)

    text: str
    section: ChunkSection
    appendix_label: str | None = None


def split_document_into_chunks(
    segments: DocumentSegments,
    *,
    count_tokens: CountTokens,
    budget: ChunkBudget,
) -> list[SectionedChunk]:
    """Chunk the body and each appendix separately.

    Splitting per segment means no chunk can straddle the boundary between the
    nämnd's reasoning and the decision it was reviewing — a chunk carrying both
    could not be honestly labelled as either.

    The trailer is deliberately not chunked: it is Sökord / Ärendenummer / Beslut,
    already captured as structured columns on `documents`, and indexing it only
    adds noise to the Swedish tsvector.
    """
    chunks = [
        SectionedChunk(text=text, section=ChunkSection.BODY)
        for text in split_into_chunks(
            segments.body,
            count_tokens=count_tokens,
            max_tokens=budget.max_tokens,
            overlap_tokens=budget.overlap_tokens,
        )
    ]
    for appendix in segments.appendices:
        chunks += [
            SectionedChunk(
                text=text,
                section=ChunkSection.APPENDIX,
                appendix_label=appendix.label,
            )
            for text in split_into_chunks(
                appendix.text,
                count_tokens=count_tokens,
                max_tokens=budget.max_tokens,
                overlap_tokens=budget.overlap_tokens,
            )
        ]
    return chunks


def split_into_chunks(
    text: str,
    *,
    count_tokens: CountTokens,
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Split text into overlapping chunks of at most `max_tokens`.

    `count_tokens` has no default. The ruler decides whether a chunk fits the
    embedding model's window, so a wrong one produces embeddings that are
    silently truncated — and a default is exactly how a wrong one comes back.
    Pass the embedding model's own counter (`ai.create_embedding_ruler`).
    """
    if not text.strip():
        return []

    sentences = _split_sentences(text)

    chunks: list[str] = []
    current: list[str] = []
    current_token_count = 0

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        if current_token_count + sentence_tokens > max_tokens and current:
            chunks.append(" ".join(current))
            current, current_token_count = _compute_overlap(
                current, overlap_tokens, count_tokens
            )

        if sentence_tokens > max_tokens and not current:
            chunks.append(sentence)
            continue

        current.append(sentence)
        current_token_count += sentence_tokens

    if current:
        chunks.append(" ".join(current))

    return chunks


def build_contextual_text(summary: str, chunk_text: str) -> str:
    return f"{summary}{CONTEXTUAL_SEPARATOR}{chunk_text}"


def truncate_summary(
    summary: str, *, count_tokens: CountTokens, max_tokens: int
) -> str:
    """Cut a summary down to the tokens reserved for it.

    The summary is prepended to every chunk, so an over-long one does not
    overflow — it displaces chunk text, and the embedding model drops the tail
    without saying so. The prompt and the role's `max_tokens` ask for a short
    summary; this is what makes it true.

    Cuts on sentence boundaries so the result still reads as prose, and falls
    back to whole words for a run-on summary whose first sentence already
    overruns — returning nothing there would strip the context from every chunk
    of that document.
    """
    if count_tokens(summary) <= max_tokens:
        return summary

    kept: list[str] = []
    total = 0
    for sentence in _split_sentences(summary):
        sentence_tokens = count_tokens(sentence)
        if total + sentence_tokens > max_tokens:
            break
        kept.append(sentence)
        total += sentence_tokens

    if kept:
        return " ".join(kept)
    return _truncate_to_words(summary, count_tokens=count_tokens, max_tokens=max_tokens)


def _truncate_to_words(text: str, *, count_tokens: CountTokens, max_tokens: int) -> str:
    kept: list[str] = []
    total = 0
    for word in text.split():
        word_tokens = count_tokens(word)
        if total + word_tokens > max_tokens:
            break
        kept.append(word)
        total += word_tokens
    return " ".join(kept)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def _compute_overlap(
    sentences: list[str], overlap_tokens: int, count_tokens: CountTokens
) -> tuple[list[str], int]:
    overlap: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        count = count_tokens(sentence)
        if total + count <= overlap_tokens:
            overlap.insert(0, sentence)
            total += count
        else:
            break
    return overlap, total
