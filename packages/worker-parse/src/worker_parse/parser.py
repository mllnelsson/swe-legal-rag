from typing import Protocol

import pypdfium2


class Parser(Protocol):
    def __call__(self, pdf_bytes: bytes) -> str: ...


class ParseError(Exception):
    pass


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
        return "\n\n---\n\n".join(pages_text)
    except pypdfium2.PdfiumError as e:
        raise ParseError(f"Failed to parse PDF: {e}") from e
