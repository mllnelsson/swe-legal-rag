from __future__ import annotations

import re

import tiktoken

MAX_TOKENS = 500
OVERLAP_TOKENS = 50
ENCODING_NAME = "cl100k_base"
CONTEXTUAL_SEPARATOR = "\n\n---\n\n"


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
