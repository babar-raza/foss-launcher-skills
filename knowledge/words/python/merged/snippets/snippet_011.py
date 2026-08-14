def test_load_markdown_from_stream(self):
        # ExStart:LoadMarkdownFromStream
        with io.BytesIO(MARKDOWN_TEXT.encode("utf-8")) as stream:
            doc = aw.Document(stream, aw.loading.MarkdownLoadOptions())
        # ExEnd:LoadMarkdownFromStream
        assert "def add" in doc.get_text()