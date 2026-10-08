def test_load_document_readsproperties(self):
        test_file = self.get_test_data_path("test.psd")

        assert Path(test_file).exists(), "Test file not found"

        with PsdImage.load(test_file) as image:
            assert image.width > 0
            assert image.height > 0
            assert image.channels > 0
            assert image.bits_per_channel == 8
            assert image.color_mode == ColorModes.RGB
            assert 0 < image.version <= 6
            assert len(image.layers) > 0