def test_numbered_list_fixture_preserves_list_markers(self) -> None:
        from aspose.note import Document
        from aspose.note.saving import PdfSaveOptions

        from tests._pdf_goldens import build_pdf_manifest

        source = fixture_path("NumberedListWithTags.one")
        if source is None:
            raise unittest.SkipTest("NumberedListWithTags.one not found")

        ensure_output_dirs()
        generated_pdf = failure_pdf_path("numbered_list_with_tags.markers")

        buf = io.BytesIO()
        Document(source).Save(buf, PdfSaveOptions())
        generated_pdf.write_bytes(buf.getvalue())

        manifest = build_pdf_manifest(generated_pdf, fixture_name="NumberedListWithTags.one")
        text = manifest["pages"][0]["text"]

        for expected in (
            "1.",
            "2.",
            "a.",
            "b.",
            "c.",
            "i.",
            "ii.",
        ):
            self.assertIn(expected, text)