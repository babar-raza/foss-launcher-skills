def test_load_basicrgb_readsmetadata(self):
        with PsdImage.load(self.get_test_data_path("basic-rgb.psd")) as image:
            assert image.width == 200
            assert image.height == 200
            assert image.channels == 3
            assert image.bits_per_channel == 8
            assert image.color_mode == ColorModes.RGB
            assert image.version == 6
            assert image.header.version == PsdHeader.PSD_VERSION
            assert image.layer_count == 3
            assert image.resource_count == 26
            assert image.compression == CompressionMethod.RLE