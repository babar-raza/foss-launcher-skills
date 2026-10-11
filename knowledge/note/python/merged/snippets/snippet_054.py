def test_richtext_rejects_legacy_keyword_aliases(self) -> None:
        from aspose.note import RichText, TextRun

        with self.assertRaises(TypeError):
            RichText(Runs=[TextRun(Text="segment")])

        with self.assertRaises(TypeError):
            RichText(FontSize=14.0)