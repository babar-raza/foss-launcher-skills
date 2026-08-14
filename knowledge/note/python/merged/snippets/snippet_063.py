def test_save_format_is_read_only(self) -> None:
        from aspose.note import SaveFormat
        from aspose.note.saving import PdfSaveOptions

        opts = PdfSaveOptions()

        with self.assertRaises(AttributeError):
            setattr(opts, "SaveFormat", SaveFormat.Pdf)