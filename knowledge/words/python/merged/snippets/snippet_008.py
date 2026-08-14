def test_open_from_bytes_io(self):
        """Load from a BytesIO stream (in-memory)."""
        file_path = Path(MY_DIR + "test_full_article.docx")
        raw = file_path.read_bytes()

        with io.BytesIO(raw) as stream:
            doc = aw.Document(stream)
        assert len(doc.get_text()) > 0