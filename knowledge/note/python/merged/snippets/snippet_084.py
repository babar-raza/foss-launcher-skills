def test_imports_smoke(self) -> None:
        import aspose.note
        import aspose.note.saving  # noqa: F401
        from aspose.note import Document, Outline, Page, ParagraphStyle, RichText  # noqa: F401
        from aspose.note.saving import PdfSaveOptions, SaveOptions  # noqa: F401

        self.assertFalse(hasattr(aspose.note, "SaveOptions"))
        self.assertFalse(hasattr(aspose.note, "PdfSaveOptions"))