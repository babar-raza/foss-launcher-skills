def test_open_document_from_file_doc_format(self):
        """Load a .doc file from a file path string."""
        doc = aw.Document(MY_DIR + "test_bold.doc")
        assert len(doc.get_text()) > 0