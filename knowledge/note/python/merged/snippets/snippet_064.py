def test_save_pdf_with_pdfsaveoptions(self) -> None:
        from aspose.note import Document
        from aspose.note.saving import PdfSaveOptions

        doc = Document(self.path)
        buf = io.BytesIO()
        doc.Save(buf, PdfSaveOptions())
        self.assertTrue(buf.getvalue().startswith(b"%PDF"))