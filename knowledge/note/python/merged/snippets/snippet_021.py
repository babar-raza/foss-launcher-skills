def test_richtext_supports_dotnet_text_runs_alias(self) -> None:
        from aspose.note import Document, RichText

        doc = Document(self.path)
        rich_text = next(rt for rt in doc.GetChildNodes(RichText) if rt.TextRuns)

        self.assertFalse(hasattr(rich_text, "Runs"))
        self.assertGreater(len(rich_text.TextRuns), 0)
        self.assertEqual(rich_text.Length, len(rich_text.Text))