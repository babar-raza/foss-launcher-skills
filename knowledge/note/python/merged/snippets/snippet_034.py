def test_title_hides_composite_child_mutators(self) -> None:
        from aspose.note import RichText, Title

        title = Title(TitleText=RichText(Text="Title"))

        self.assertIs(next(iter(title)), title.TitleText)
        for member in ("FirstChild", "LastChild", "AppendChildFirst", "AppendChildLast", "InsertChild", "RemoveChild"):
            self.assertFalse(hasattr(title, member), member)