def test_document_keeps_subpages_from_multiple_page_spaces(self) -> None:
        from aspose.note import Document, Outline, OutlineElement, Page, RichText

        doc = Document(self.path)
        pages = doc.GetChildNodes(Page)

        self.assertEqual(len(list(doc)), 2)
        self.assertEqual(len(pages), 2)
        self.assertEqual(
            [page.Title.TitleText.Text if page.Title and page.Title.TitleText else None for page in pages],
            ["Page1", "Subpage2"],
        )
        self.assertEqual([page.Level for page in pages], [1, 2])

        page_texts: list[list[str]] = []
        for page in pages:
            texts: list[str] = []
            for outline in page.GetChildNodes(Outline):
                for outline_element in outline.GetChildNodes(OutlineElement):
                    texts.extend(rich_text.Text for rich_text in outline_element.GetChildNodes(RichText) if rich_text.Text)
            page_texts.append(texts)

        self.assertEqual(page_texts, [["Content1"], ["Content2"]])