def test_open_from_stream(self):
        """Load a document from a binary stream."""
        # ExStart:OpeningFromStream
        with io.FileIO(MY_DIR + "test_full_article.docx") as stream:
            doc = aw.Document(stream)
        # ExEnd:OpeningFromStream
        assert len(doc.get_text()) > 0