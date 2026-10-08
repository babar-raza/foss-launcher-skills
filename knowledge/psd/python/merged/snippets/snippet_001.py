def test_image_load_official_returns_psd(self):
        with Image.load(self.get_test_data_path("test.psd")) as image:
            psd_image = image  # Image.load returns a PsdImage instance
            assert psd_image.width == 100
            assert psd_image.channels_count == 3
            assert len(psd_image.layers) == 2