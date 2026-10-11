def test_save_format_exports_only_pdf(self) -> None:
        from aspose.note import SaveFormat

        self.assertEqual(list(SaveFormat), [SaveFormat.Pdf])