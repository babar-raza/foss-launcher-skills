def test_page_clone_accepts_clone_history_keyword(self) -> None:
        from aspose.note import Document, Page

        page = Document(self.path).GetChildNodes(Page)[0]
        cloned = page.Clone(cloneHistory=True)

        self.assertIsNot(cloned, page)