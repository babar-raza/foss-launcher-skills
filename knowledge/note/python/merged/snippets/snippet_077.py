def test_pdf_writer_uses_unicode_font_for_cyrillic(self) -> None:
        from aspose.note.saving.pdf_writer import _REGISTERED_FONT_NAMES, _font_name_for_style

        style = SimpleNamespace(FontName=None, IsBold=False, IsItalic=False)
        _REGISTERED_FONT_NAMES.clear()
        self.addCleanup(_REGISTERED_FONT_NAMES.clear)

        with patch("aspose.note.saving.pdf_writer._find_font_file", return_value=("DejaVuSans", Path("/tmp/DejaVuSans.ttf"))), patch(
            "reportlab.pdfbase.pdfmetrics.getRegisteredFontNames", return_value=[]
        ), patch("reportlab.pdfbase.pdfmetrics.registerFont") as register_font, patch("reportlab.pdfbase.ttfonts.TTFont") as ttfont:
            font_name = _font_name_for_style(style, "Arial", text="Привет")

        self.assertEqual(font_name, "DejaVuSans")
        ttfont.assert_called_once()
        self.assertEqual(ttfont.call_args.args[0], "DejaVuSans")
        self.assertTrue(str(ttfont.call_args.args[1]).endswith("DejaVuSans.ttf"))
        register_font.assert_called_once()