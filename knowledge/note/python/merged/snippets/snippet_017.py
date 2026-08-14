def test_construct_from_stream(self) -> None:
        from aspose.note import Document

        doc = Document(io.BytesIO(self.data))
        self.assertGreater(len(list(doc)), 0)