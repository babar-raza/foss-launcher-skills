def test_construct_from_path(self) -> None:
        from aspose.note import Document

        doc = Document(self.path)
        self.assertFalse(hasattr(doc, "Count"))
        self.assertGreater(len(list(doc)), 0)
        self.assertIsNotNone(doc.FirstChild)
        self.assertIsNotNone(doc.LastChild)