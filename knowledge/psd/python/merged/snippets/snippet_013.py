def test_load_indexedfixture_readsdata(self):
        with PsdImage.load(self.get_test_data_path("basic-indexed.psd")) as image:
            assert image.width == 200
            assert image.height == 200
            assert image.channels == 1
            assert image.color_mode == ColorModes.INDEXED
            assert image.has_color_mode_data is True
            assert image.color_data_info.kind == PsdColorDataKind.INDEXED_PALETTE
            assert image.color_data_info.raw_data_length == 768
            assert image.layer_count == 0
            assert image.resource_count == 24