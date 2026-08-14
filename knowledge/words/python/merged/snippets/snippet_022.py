def test_pretty_format_round_trip(self):
        """Pretty-formatted DOCX should produce the same text after reload."""
        # ExStart:PrettyFormatRoundTrip
        save_options = aw.saving.OoxmlSaveOptions()
        save_options.pretty_format = True

        self.convert(
            "test_full_article.docx",
            "OoxmlSaveOptions.pretty_roundtrip.docx",
            save_options=save_options,
        )

        original = aw.Document(
            str(Path(ARTIFACTS_DIR) / ".." / ".." / "tests" / "data" / "input" / "test_full_article.docx")
        )
        reloaded = aw.Document(str(Path(ARTIFACTS_DIR) / "OoxmlSaveOptions.pretty_roundtrip.docx"))
        # ExEnd:PrettyFormatRoundTrip

        assert original.get_text().strip() == reloaded.get_text().strip()