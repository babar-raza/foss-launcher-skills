def test_images_are_identical_by_hash(self) -> None:
        from aspose.note import Document, Image

        doc = Document(self.path)
        images = doc.GetChildNodes(Image)
        self.assertEqual(len(images), 3)

        digests = [hashlib.sha256(bytes(img.Bytes)).digest() for img in images]
        self.assertEqual(len(set(digests)), 1)