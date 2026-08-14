def test_single_page_fixtures_do_not_create_synthetic_titles(self) -> None:
        from aspose.note import Document, Page

        for fixture_name in ("SimpleTable.one", "3ImagesWithDifferentAlignment.one"):
            path = _fixture_path(fixture_name)
            if path is None:
                raise unittest.SkipTest(f"{fixture_name} not found")

            doc = Document(path)
            pages = doc.GetChildNodes(Page)

            self.assertEqual(len(pages), 1)
            self.assertIsNone(pages[0].Title, fixture_name)
            self.assertEqual(pages[0].Level, 1, fixture_name)