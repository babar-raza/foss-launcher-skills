def test_save_non_pdf_path_raises(self) -> None:
        from aspose.note import Document, UnsupportedSaveFormatException

        doc = Document(self.path)
        with self.assertRaises(UnsupportedSaveFormatException):
            doc.Save("unsupported-output.one")