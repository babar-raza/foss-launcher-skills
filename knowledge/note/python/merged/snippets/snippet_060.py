def test_pdf_save_options_roundtrip(self) -> None:
        from aspose.note import SaveFormat
        from aspose.note.saving import PdfSaveOptions

        opts = PdfSaveOptions()
        self.assertEqual(opts.SaveFormat, SaveFormat.Pdf)
        self.assertEqual(opts.PageIndex, 0)
        self.assertIsNone(opts.PageCount)
        self.assertFalse(hasattr(opts, "TagIconDir"))
        self.assertFalse(hasattr(opts, "TagIconSize"))
        self.assertFalse(hasattr(opts, "TagIconGap"))