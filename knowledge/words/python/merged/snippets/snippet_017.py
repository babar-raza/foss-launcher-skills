def test_set_encoding(self):
        # ExStart:SetEncoding
        save_options = aw.saving.MarkdownSaveOptions()
        save_options.encoding = "utf-16"

        self.convert(
            "test_full_article.docx",
            "MarkdownSaveOptions.encoding_utf16.md",
            save_options=save_options,
        )
        # ExEnd:SetEncoding

        output = Path(ARTIFACTS_DIR) / "MarkdownSaveOptions.encoding_utf16.md"
        raw = output.read_bytes()
        assert raw[:2] == b"\xff\xfe", "UTF-16 LE BOM expected"
        assert "Introduction" in raw.decode("utf-16")