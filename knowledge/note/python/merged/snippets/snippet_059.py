def test_root_namespace_does_not_export_save_options(self) -> None:
        import aspose.note

        self.assertFalse(hasattr(aspose.note, "SaveOptions"))
        self.assertFalse(hasattr(aspose.note, "PdfSaveOptions"))