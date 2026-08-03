import uuid

from shared.storage import document_pdf_key


class TestDocumentPdfKey:
    def test_key_layout_is_stable(self):
        """The download worker writes this key, the parse worker reads it and the
        API serves it, so its shape is a cross-package contract."""
        document_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
        assert (
            document_pdf_key(document_id)
            == "documents/11111111-2222-3333-4444-555555555555/original.pdf"
        )

    def test_distinct_documents_get_distinct_keys(self):
        assert document_pdf_key(uuid.uuid4()) != document_pdf_key(uuid.uuid4())
