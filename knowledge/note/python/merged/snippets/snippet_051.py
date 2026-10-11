def test_paragraphstyle_exposes_default_text_properties(self) -> None:
        from aspose.note import ParagraphStyle

        style = ParagraphStyle.Default
        style.FontName = "Courier New"
        style.FontSize = 20.0
        style.FontColor = 0x112233
        style.Highlight = 0xAABBCC
        style.IsBold = True
        style.IsItalic = True
        style.IsUnderline = True
        style.IsStrikethrough = True
        style.IsSuperscript = True
        style.IsSubscript = True

        self.assertEqual(style.FontName, "Courier New")
        self.assertEqual(style.FontSize, 20.0)
        self.assertEqual(style.FontColor, 0x112233)
        self.assertEqual(style.Highlight, 0xAABBCC)
        self.assertEqual(style.FontStyle, 15)
        self.assertFalse(hasattr(style, "Alignment"))
        self.assertFalse(hasattr(style, "Language"))