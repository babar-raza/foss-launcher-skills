def test_incremental_history_reconstructs_image_alignment_versions(self) -> None:
        from aspose.note import Document, LoadOptions, Page

        fixture_path = _fixture_path("3ImagesWithDifferentAlignment.one")
        if fixture_path is None:
            raise unittest.SkipTest("3ImagesWithDifferentAlignment.one not found")

        doc = Document(fixture_path, LoadOptions(LoadHistory=True))
        page = doc.GetChildNodes(Page)[0]
        history = doc.GetPageHistory(page)
        texts = [_page_body_text(item) for item in history]

        self.assertEqual(_page_body_text(page), "Image in the outline with left alignment")
        self.assertEqual(_page_body_text(history.Current), "Image in the outline with left alignment")
        self.assertEqual(texts[:3], ["", "fdf", "0"])
        self.assertTrue(all(text == "tt" for text in texts[3:]))