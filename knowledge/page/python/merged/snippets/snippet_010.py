def test_encode_png_and_bmp_signatures(self) -> None:
        doc = RenderDocument()
        doc.pages.append(RenderPage(width=8, height=8))
        surface = RasterRenderer(dpi=72).render(doc)
        png = encode_png(surface)
        bmp = encode_bmp(surface)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(bmp.startswith(b"BM"))