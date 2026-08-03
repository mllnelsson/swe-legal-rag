import uuid

_DOCUMENT_PDF_KEY = "documents/{document_id}/original.pdf"


def document_pdf_key(document_id: uuid.UUID) -> str:
    """Storage key of a decision's original PDF.

    The download worker writes it, the parse worker reads it and the API serves
    it, so the layout is a shared contract rather than any one caller's detail.
    """
    return _DOCUMENT_PDF_KEY.format(document_id=document_id)
