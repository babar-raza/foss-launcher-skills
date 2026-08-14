def test_incremental_history_reconstructs_simple_table_versions(self) -> None:
        from aspose.note import Document, LoadOptions, Page

        fixture_path = _fixture_path("SimpleTable.one")
        if fixture_path is None:
            raise unittest.SkipTest("SimpleTable.one not found")

        doc = Document(fixture_path, LoadOptions(LoadHistory=True))
        page = doc.GetChildNodes(Page)[0]
        history = doc.GetPageHistory(page)
        texts = [_page_body_text(item) for item in history]

        self.assertEqual(_page_body_text(page), "0")
        self.assertEqual(_page_body_text(history.Current), "0")
        self.assertEqual(texts, ["", "fdf"])