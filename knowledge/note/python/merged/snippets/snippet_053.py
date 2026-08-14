def test_richtext_append_without_explicit_style_uses_paragraphstyle_defaults(self) -> None:
        from aspose.note import ParagraphStyle, RichText

        rich_text = RichText(ParagraphStyle=ParagraphStyle(FontName="Courier New", FontSize=18.0, IsItalic=True))
        rich_text.Append("First")
        rich_text.Append("Second")

        self.assertEqual([run.Text for run in rich_text.TextRuns], ["First", "Second"])
        for run in rich_text.TextRuns:
            self.assertEqual(run.Style.FontName, "Courier New")
            self.assertEqual(run.Style.FontSize, 18.0)
            self.assertTrue(run.Style.IsItalic)