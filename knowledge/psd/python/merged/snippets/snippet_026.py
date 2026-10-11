def test_save_layervariants_clipping(self):
        test_file = self.get_test_data_path("layer-variants.psd")
        output_file = self.get_persistent_artifact_path(
            "layer_variants_clipping_test.psd"
        )

        with PsdImage.load(test_file) as image:
            image.layers[3].clipping = 0
            image.save(output_file)
        self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[3].clipping == 0