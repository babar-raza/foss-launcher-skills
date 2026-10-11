def test_image_uses_alignment_without_legacy_alias(self) -> None:
        from aspose.note import HorizontalAlignment, Image

        image = Image(Bytes=b"img", Width=10.0, Height=20.0, Alignment=HorizontalAlignment.Center)

        self.assertEqual(image.Alignment, HorizontalAlignment.Center)
        self.assertFalse(hasattr(image, "HorizontalAlignment"))