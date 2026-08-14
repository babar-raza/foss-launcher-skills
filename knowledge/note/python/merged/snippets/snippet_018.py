def test_document_file_format_enum(self) -> None:
        from aspose.note import Document, FileFormat

        doc = Document(self.path)
        self.assertIsInstance(doc.FileFormat, FileFormat)