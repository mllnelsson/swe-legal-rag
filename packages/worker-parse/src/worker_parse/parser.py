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


class Parser(Protocol):
    def __call__(self, pdf_bytes: bytes) -> str: ...


class ParseError(Exception):
    pass


def normalize_typographic_chars(text: str) -> str:
    return text.translate(_TYPOGRAPHIC_CHAR_MAP)


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
        return normalize_typographic_chars(text)
    except pypdfium2.PdfiumError as e:
        raise ParseError(f"Failed to parse PDF: {e}") from e
