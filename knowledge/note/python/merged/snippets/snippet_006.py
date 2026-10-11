def test_images_exposed_and_have_bytes(self) -> None:
        from aspose.note import Document, Image

        doc = Document(self.path)
        images = doc.GetChildNodes(Image)
        self.assertEqual(len(images), 3)
        self.assertTrue(all(isinstance(img.Bytes, (bytes, bytearray)) for img in images))
        self.assertTrue(all(len(img.Bytes) > 1024 for img in images))