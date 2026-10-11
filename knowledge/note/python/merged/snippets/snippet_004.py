def test_open_and_save_pdf_to_stream(self) -> None:
        from aspose.note import Document, SaveFormat

        doc = Document(self.path)
        self.assertFalse(hasattr(doc, "Count"))
        self.assertGreater(len(list(doc)), 0)

        buf = io.BytesIO()
        doc.Save(buf, SaveFormat.Pdf)
        data = buf.getvalue()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 100)