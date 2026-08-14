def test_table_with_tag_exposes_tags(self) -> None:
        p = _fixture_path("TableWithTag.one")
        if p is None:
            raise unittest.SkipTest("TableWithTag.one not found")

        from aspose.note import Document, Table

        doc = Document(p)
        tables = doc.GetChildNodes(Table)
        self.assertGreaterEqual(len(tables), 1)

        tagged = [t for t in tables if getattr(t, "Tags", None)]
        self.assertGreaterEqual(len(tagged), 1)
        self.assertTrue(any(_tag_is_meaningful(tag) for t in tagged for tag in t.Tags))