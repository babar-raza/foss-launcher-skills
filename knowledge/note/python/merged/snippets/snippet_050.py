def test_richtext_stores_alignment_on_richtext(self) -> None:
        from aspose.note import HorizontalAlignment, ParagraphStyle, RichText

        with self.assertRaises(TypeError):
            ParagraphStyle(Alignment=HorizontalAlignment.Center)

        paragraph_style = ParagraphStyle()
        rich_text = RichText(Text="Aligned", ParagraphStyle=paragraph_style, Alignment=HorizontalAlignment.Center)

        self.assertEqual(rich_text.Alignment, HorizontalAlignment.Center)
        self.assertFalse(hasattr(rich_text.ParagraphStyle, "Alignment"))