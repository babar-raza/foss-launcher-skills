def test_richtext_uses_paragraphstyle_as_default_text_style(self) -> None:
        from aspose.note import ParagraphStyle, RichText

        paragraph_style = ParagraphStyle(FontName="Courier New", FontSize=20.0, IsBold=True, Highlight=0xFFFF00)
        rich_text = RichText(Text="Paragraph defaults", ParagraphStyle=paragraph_style)

        self.assertEqual(len(rich_text.TextRuns), 1)
        run_style = rich_text.TextRuns[0].Style
        self.assertEqual(run_style.FontName, "Courier New")
        self.assertEqual(run_style.FontSize, 20.0)
        self.assertTrue(run_style.IsBold)
        self.assertEqual(run_style.Highlight, 0xFFFF00)