def test_load_layers_indexable(self):
        test_file = self.get_test_data_path("test.psd")

        with PsdImage.load(test_file) as image:
            assert image.layers[0] is not None
            assert image.layers[1] is not None