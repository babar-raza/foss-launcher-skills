def test_images_expose_dotnet_compatibility_metadata(self) -> None:
        from aspose.note import Document, Image

        image = Document(self.path).GetChildNodes(Image)[0]

        self.assertEqual(image.OriginalWidth, image.Width)
        self.assertEqual(image.OriginalHeight, image.Height)
        self.assertFalse(hasattr(image, "HorizontalAlignment"))