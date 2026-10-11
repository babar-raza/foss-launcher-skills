def test_page_history_constructor_accepts_only_current_page(self) -> None:
        from aspose.note import Page, PageHistory

        current = Page()
        history = PageHistory(current)

        self.assertIs(history.Current, current)

        with self.assertRaises(TypeError):
            PageHistory(current, [Page()])