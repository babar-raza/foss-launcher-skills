def test_open_document_from_file(self):
        """Load a document from a file path string."""
        # ExStart:OpenDocument
        doc = aw.Document(MY_DIR + "test_full_article.docx")
        # ExEnd:OpenDocument
        assert len(doc.get_text()) > 0