def test_save_with_pdf_save_options(self):
        """PdfSaveOptions is accepted for API compatibility."""
        # ExStart:SaveWithPdfSaveOptions
        save_options = aw.saving.PdfSaveOptions()
        self.convert(
            "test_full_article.docx",
            "PdfSaveOptions.with_options.pdf",
            save_options=save_options,
        )
        # ExEnd:SaveWithPdfSaveOptions