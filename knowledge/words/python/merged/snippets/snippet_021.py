def test_pretty_format_off(self):
        # ExStart:PrettyFormatOff
        save_options = aw.saving.OoxmlSaveOptions()
        save_options.pretty_format = False

        self.convert(
            "test_full_article.docx",
            "OoxmlSaveOptions.compact.docx",
            save_options=save_options,
        )
        # ExEnd:PrettyFormatOff

        output = Path(ARTIFACTS_DIR) / "OoxmlSaveOptions.compact.docx"
        with zipfile.ZipFile(output) as zf:
            doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert len(doc_xml.splitlines()) == 1, "Compact mode: whole part on one line"