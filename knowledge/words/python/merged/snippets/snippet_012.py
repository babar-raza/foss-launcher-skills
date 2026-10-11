def test_markdown_round_trip_preserves_source(self):
        # ExStart:MarkdownRoundTrip
        doc = aw.Document(io.BytesIO(MARKDOWN_TEXT.encode("utf-8")), aw.loading.MarkdownLoadOptions())
        doc.save(ARTIFACTS_DIR + "LoadingMarkdown.RoundTrip.md", aw.SaveFormat.MARKDOWN)
        # ExEnd:MarkdownRoundTrip

        result = Path(ARTIFACTS_DIR + "LoadingMarkdown.RoundTrip.md").read_text(
            encoding="utf-8-sig"
        ).replace("\r\n", "\n")

        assert "# Release Notes" in result
        assert "**bold**" in result
        assert "*italic*" in result
        assert "`inline code`" in result
        assert "[project link](https://example.com)" in result
        assert "- Parses headings, emphasis, and lists" in result
        assert "- Round-trips fenced code blocks unchanged" in result
        assert "def add(a, b):\n    return a + b" in result
        assert "def subtract(a, b):\n    return a - b" in result