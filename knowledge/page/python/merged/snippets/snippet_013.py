def test_xps_to_bmp_header(self) -> None:
        path = os.path.join("testdata", "xps", "integration", "Simple.xps")
        doc = XpsDocument.from_file(path)
        data = doc.to_image(ImageSaveOptions(format="bmp", dpi=72))
        self.assertTrue(data.startswith(b"BM"))