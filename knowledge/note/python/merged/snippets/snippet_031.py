def test_parent_node_is_read_only_to_callers(self) -> None:
        from aspose.note import Document, Page

        doc = Document()
        page = Page()
        doc.AppendChildLast(page)

        self.assertIs(page.ParentNode, doc)

        with self.assertRaises(AttributeError):
            setattr(page, "ParentNode", None)