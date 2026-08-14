def test_get_page_history_returns_all_revisions_in_order(self) -> None:
        from aspose.note import Document, LoadOptions, Page

        doc = Document(self.path, LoadOptions(LoadHistory=True))
        page = doc.GetChildNodes(Page)[0]

        history = doc.GetPageHistory(page)

        self.assertEqual(_page_body_text(history.Current), "Third text")
        self.assertEqual([_page_body_text(item) for item in history], ["", "First text", "Second text"])