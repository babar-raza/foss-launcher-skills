def test_get_child_nodes_page_and_title(self) -> None:
        from aspose.note import Document, Page, Title

        doc = Document(self.path)
        pages = doc.GetChildNodes(Page)
        self.assertGreaterEqual(len(pages), 1)

        titles = doc.GetChildNodes(Title)
        # Each page should have a Title node.
        self.assertGreaterEqual(len(titles), len(pages))

        # Page.Title property should match first Title in its children.
        page0 = pages[0]
        self.assertIsNotNone(page0.Title)
        self.assertIs(page0.FirstChild, page0.Title)