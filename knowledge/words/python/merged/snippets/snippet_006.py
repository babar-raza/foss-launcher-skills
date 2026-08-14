def test_open_from_stream_doc_format(self):
        """Load a .doc document from a stream (auto-detected)."""
        with io.FileIO(MY_DIR + "test_bold.doc") as stream:
            doc = aw.Document(stream)
        assert len(doc.get_text()) > 0