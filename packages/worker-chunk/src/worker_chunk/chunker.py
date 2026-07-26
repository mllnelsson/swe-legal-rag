from __future__ import annotations

import re

import tiktoken
from pydantic import BaseModel, ConfigDict

from shared.enums import ChunkSection
from shared.segmentation import DocumentSegments

MAX_TOKENS = 500
OVERLAP_TOKENS = 50
ENCODING_NAME = "cl100k_base"
CONTEXTUAL_SEPARATOR = "\n\n---\n\n"


class SectionedChunk(BaseModel):
    """A chunk plus the provenance retrieval needs to keep instances apart."""

    model_config = ConfigDict(frozen=True)

    text: str
    section: ChunkSection
    appendix_label: str | None = None


def split_document_into_chunks(
    segments: DocumentSegments,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
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
        for text in split_into_chunks(segments.body, max_tokens, overlap_tokens)
    ]
    for appendix in segments.appendices:
        chunks += [
            SectionedChunk(
                text=text,
                section=ChunkSection.APPENDIX,
                appendix_label=appendix.label,
            )
            for text in split_into_chunks(appendix.text, max_tokens, overlap_tokens)
        ]
    return chunks


def split_into_chunks(
    text: str,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    encoding_name: str = ENCODING_NAME,
) -> list[str]:
    if not text.strip():
        return []

    enc = tiktoken.get_encoding(encoding_name)
    sentences = _split_sentences(text)

    chunks: list[str] = []
    current: list[str] = []
    current_token_count = 0

    for sentence in sentences:
        sentence_tokens = len(enc.encode(sentence))

        if current_token_count + sentence_tokens > max_tokens and current:
            chunks.append(" ".join(current))
            current, current_token_count = _compute_overlap(
                current, overlap_tokens, enc
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


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def _compute_overlap(
    sentences: list[str], overlap_tokens: int, enc: tiktoken.Encoding
) -> tuple[list[str], int]:
    overlap: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        count = len(enc.encode(sentence))
        if total + count <= overlap_tokens:
            overlap.insert(0, sentence)
            total += count
        else:
            break
    return overlap, total
