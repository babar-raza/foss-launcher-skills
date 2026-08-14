def test_export_underline_formatting(self):
        # ExStart:ExportUnderlineFormatting
        save_options = aw.saving.MarkdownSaveOptions()
        save_options.export_underline_formatting = True

        self.convert(
            "test_underline_text.docx",
            "MarkdownSaveOptions.export_underline.md",
            save_options=save_options,
        )
        # ExEnd:ExportUnderlineFormatting