def test_encode_jpeg_non_empty(self) -> None:
        doc = RenderDocument()
        doc.pages.append(RenderPage(width=8, height=8))
        surface = RasterRenderer(dpi=72).render(doc)
        jpeg = encode_jpeg(surface)
        self.assertTrue(jpeg.startswith(b"\xFF\xD8"))
        self.assertGreater(len(jpeg), 4)