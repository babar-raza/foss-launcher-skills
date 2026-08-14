def test_page_clone_duplicates_content_tree(self) -> None:
        from aspose.note import Document, Page, RichText

        page = Document(self.path).GetChildNodes(Page)[0]
        cloned = page.Clone()

        self.assertIsNot(cloned, page)
        self.assertEqual(len(list(cloned)), len(list(page)))
        self.assertEqual(len(cloned.GetChildNodes(RichText)), len(page.GetChildNodes(RichText)))
        self.assertIsNone(cloned.ParentNode)