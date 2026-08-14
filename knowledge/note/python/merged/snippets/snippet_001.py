def test_imports(self) -> None:
        import aspose  # noqa: F401
        import aspose.note  # noqa: F401

        from aspose.note import (  # noqa: F401
            Document,
            SaveFormat,
            FileFormat,
            License,
            Metered,
            ParagraphStyle,
        )
        from aspose.note.saving import PdfSaveOptions  # noqa: F401