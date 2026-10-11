def test_save_pdf_infers_format_from_path_extension(self) -> None:
        from aspose.note import Document

        doc = Document(self.path)
        output = Path("tests/out/pdf_export/inferred_extension_save.pdf")
        output.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(output.unlink, missing_ok=True)

        doc.Save(output)

        self.assertTrue(output.read_bytes().startswith(b"%PDF"))