def test_load_layervariants_readsflags(self):
        with PsdImage.load(self.get_test_data_path("layer-variants.psd")) as image:
            assert image.layer_count == 4
            assert image.layers[1].is_visible is False
            assert image.layers[2].blend_mode_key == BlendMode.LINEARBURN
            assert image.layers[2].raw_blend_mode_key == "lbrn"
            assert image.layers[3].clipping == 1
            assert image.layers[3].additional_layer_data