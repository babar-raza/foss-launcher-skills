def test_pdf_writer_uses_base14_fonts_by_default(self) -> None:
        from aspose.note.saving.pdf_writer import _register_font_variant

        self.assertEqual(_register_font_variant("sans", False, False), "Helvetica")
        self.assertEqual(_register_font_variant("serif", False, True), "Times-Italic")