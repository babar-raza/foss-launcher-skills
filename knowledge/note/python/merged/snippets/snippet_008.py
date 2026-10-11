def test_images_preserve_outline_alignment(self) -> None:
        from aspose.note import Document, HorizontalAlignment, Image

        doc = Document(self.path)
        images = doc.GetChildNodes(Image)

        self.assertEqual(
            [image.Alignment for image in images],
            [
                HorizontalAlignment.Right,
                HorizontalAlignment.Center,
                HorizontalAlignment.Left,
            ],
        )