import re
from typing import Protocol

import pypdfium2

# Word's "smart" autocorrect writes these typographic variants instead of the
# plain ASCII characters our downstream regex-based extractors expect (e.g.
# case numbers like "2025-0008" render as "2025–0008" in the source PDF).
# Normalizing right after extraction means every metadata pattern can assume
# ASCII punctuation without each one handling this itself.
_TYPOGRAPHIC_CHAR_MAP = str.maketrans(
    {
        "‐": "-",  # hyphen
        "‑": "-",  # non-breaking hyphen
        "‒": "-",  # figure dash
        "–": "-",  # en dash
        "—": "-",  # em dash
        "―": "-",  # horizontal bar
        "−": "-",  # minus sign
        "‘": "'",  # left single quotation mark
        "’": "'",  # right single quotation mark
        "“": '"',  # left double quotation mark
        "”": '"',  # right double quotation mark
    }
)


# pypdfium2 emits U+FFFE — a Unicode noncharacter — where the source PDF hyphenated
# a word across a line break. It arrives with the newline already removed, so the two
# halves are one contiguous token: "hand￾lingsoffentligheten". Left alone, Postgres
# tokenizes that as 'hand' + 'lingsoffent' instead of 'handlingsoffent', so a search for
# the term the decision is actually about does not match the chunk containing it.
_HYPHENATION_MARK = "￾"

# Most such hyphens are purely typographic and the word rejoins without one
# (hand-lingsoffentligheten, advokat-firman). The exception is a lexical hyphen that
# happened to fall at the wrap: Swedish forms these on a one- or two-letter stem
# (e-post, u-land, tv-licens), so a short left fragment keeps its hyphen.
_LEXICAL_HYPHEN_STEM_MAX = 2
_HYPHENATION_RE = re.compile(rf"(\w*){_HYPHENATION_MARK}(\w*)")


class Parser(Protocol):
    def __call__(self, pdf_bytes: bytes) -> str: ...


class ParseError(Exception):
    pass


def normalize_typographic_chars(text: str) -> str:
    return text.translate(_TYPOGRAPHIC_CHAR_MAP)


def rejoin_hyphenated_words(text: str) -> str:
    """Repair words split by a line-break hyphen, keeping lexical hyphens."""

    def repair(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        separator = "-" if 0 < len(left) <= _LEXICAL_HYPHEN_STEM_MAX else ""
        return f"{left}{separator}{right}"

    return _HYPHENATION_RE.sub(repair, text)


def parse_pdf_with_pypdfium2(pdf_bytes: bytes) -> str:
    try:
        doc = pypdfium2.PdfDocument(pdf_bytes)
        pages_text = []
        for page in doc:
            textpage = page.get_textpage()
            pages_text.append(textpage.get_text_range())
            textpage.close()
            page.close()
        doc.close()
        text = "\n\n---\n\n".join(pages_text)
        return rejoin_hyphenated_words(normalize_typographic_chars(text))
    except pypdfium2.PdfiumError as e:
        raise ParseError(f"Failed to parse PDF: {e}") from e
