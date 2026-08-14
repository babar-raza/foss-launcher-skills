def test_load_markdown_from_bytes(self):
        # ExStart:LoadMarkdownFromBytes
        doc = aw.Document(io.BytesIO(MARKDOWN_TEXT.encode("utf-8")), aw.loading.MarkdownLoadOptions())
        # ExEnd:LoadMarkdownFromBytes
        assert "Release Notes" in doc.get_text()