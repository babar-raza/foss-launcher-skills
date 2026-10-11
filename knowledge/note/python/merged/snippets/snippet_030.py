def test_document_does_not_expose_non_dotnet_count_method(self) -> None:
        from aspose.note import Document, Page

        doc = Document()
        doc.AppendChildLast(Page())

        self.assertFalse(hasattr(doc, "Count"))
        self.assertEqual(len(list(doc)), 1)