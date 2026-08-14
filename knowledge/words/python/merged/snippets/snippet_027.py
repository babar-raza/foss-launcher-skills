def test_get_text(self):
        """Extract text via get_text() without saving to file."""
        # ExStart:GetText
        doc = aw.Document(MY_DIR + "test_full_article.docx")
        text = doc.get_text()
        assert len(text) > 0
        # ExEnd:GetText