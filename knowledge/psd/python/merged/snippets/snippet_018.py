def test_load_basiccmyk_readsmetadata(self):
        with PsdImage.load(self.get_test_data_path("basic-cmyk.psd")) as image:
            assert image.width == 200
            assert image.height == 200
            assert image.channels == 4
            assert image.color_mode == ColorModes.CMYK
            assert image.layer_count == 3
            assert image.resource_count == 28
            assert image.compression == CompressionMethod.RLE
            assert len(image.image_data_info.row_byte_counts) == 800