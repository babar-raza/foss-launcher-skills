def test_title_nodes_are_visible(self) -> None:
        from aspose.note import Document, Title

        doc = Document(self.path)
        titles = doc.GetChildNodes(Title)
        self.assertGreaterEqual(len(titles), 1)