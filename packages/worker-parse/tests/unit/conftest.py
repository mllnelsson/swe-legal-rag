import ctypes
import io

import pypdfium2 as pdfium
import pypdfium2.raw as r
import pytest


def _make_pdf_bytes(text: str = "Test Content") -> bytes:
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(200, 200)
    textobj = r.FPDFPageObj_NewTextObj(doc, b"Helvetica", 14.0)
    encoded = (text + "\x00").encode("utf-16-le")
    ushort_array = (ctypes.c_ushort * (len(encoded) // 2)).from_buffer_copy(encoded)
    r.FPDFText_SetText(textobj, ushort_array)
    r.FPDFPageObj_Transform(textobj, 1, 0, 0, 1, 10, 100)
    r.FPDFPage_InsertObject(page, textobj)
    r.FPDFPage_GenerateContent(page)
    page.close()
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    pdf_bytes = buf.read()
    doc.close()
    return pdf_bytes


@pytest.fixture(scope="session")
def minimal_pdf_bytes() -> bytes:
    return _make_pdf_bytes("Test Content")
