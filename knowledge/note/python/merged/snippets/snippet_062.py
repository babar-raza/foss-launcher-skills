def test_save_options_expose_common_base_properties(self) -> None:
        from aspose.note import SaveFormat
        from aspose.note.saving import PdfSaveOptions

        opts = PdfSaveOptions(PageIndex=2, PageCount=3, FontsSubsystem="fonts-subsystem")
        self.assertEqual(opts.SaveFormat, SaveFormat.Pdf)
        self.assertEqual(opts.PageIndex, 2)
        self.assertEqual(opts.PageCount, 3)
        self.assertEqual(opts.FontsSubsystem, "fonts-subsystem")