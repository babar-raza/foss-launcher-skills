def test_load_layerinspection_readsvalues(self):
        path = self.get_test_data_path("test.psd")
        with PsdImage.load(path) as image:
            first_layer = image.layers[0]

            assert first_layer.bounds == Rectangle(0, 0, 100, 100)
            assert first_layer.width == first_layer.bounds.width
            assert first_layer.height == first_layer.bounds.height
            assert first_layer.top == 0
            assert first_layer.left == 0
            assert first_layer.bottom == 100
            assert first_layer.right == 100
            assert first_layer.channels_count > 0
            assert len(first_layer.raw_blend_mode_key) == 4
            assert first_layer.layer_mask_data is None
            assert first_layer.layer_blending_ranges_data.length == (
                first_layer.blending_ranges_info.raw_data_length - 4
            )
            assert first_layer.additional_layer_data