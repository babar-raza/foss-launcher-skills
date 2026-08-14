def test_textstyle_uses_dotnet_property_names_only(self) -> None:
        from aspose.note import TextStyle

        style = TextStyle.Default
        style.IsBold = True
        style.IsItalic = True
        style.IsUnderline = True
        style.IsStrikethrough = True
        style.IsSuperscript = True
        style.IsSubscript = True
        style.Highlight = 123
        style.Language = 1031

        self.assertFalse(hasattr(style, "Bold"))
        self.assertFalse(hasattr(style, "Italic"))
        self.assertFalse(hasattr(style, "Underline"))
        self.assertFalse(hasattr(style, "Strikethrough"))
        self.assertFalse(hasattr(style, "Superscript"))
        self.assertFalse(hasattr(style, "Subscript"))
        self.assertFalse(hasattr(style, "HighlightColor"))
        self.assertFalse(hasattr(style, "HorizontalAlignment"))
        self.assertFalse(hasattr(style, "LanguageId"))
        self.assertEqual(style.Highlight, 123)
        self.assertEqual(style.Language, 1031)