def test_load_layer_readsproperties(self):
        test_file = self.get_test_data_path("test.psd")

        with PsdImage.load(test_file) as image:
            assert len(image.layers) > 0

            first_layer = image.layers[0]

            assert first_layer.name == "Background copy"
            assert first_layer.bounds != Rectangle()
            assert first_layer.is_visible is True
            assert 0 <= first_layer.opacity <= 255
            assert first_layer.blend_mode_key == BlendMode.NORMAL

            assert image.layers[1].name == "Pattern Fill 1"