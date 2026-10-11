def test_textstyle_rejects_legacy_keyword_aliases(self) -> None:
        from aspose.note import TextStyle

        for kwargs in (
            {"Bold": True},
            {"Italic": True},
            {"Underline": True},
            {"Strikethrough": True},
            {"Superscript": True},
            {"Subscript": True},
            {"HighlightColor": 123},
            {"LanguageId": 1031},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(TypeError):
                    TextStyle(**kwargs)