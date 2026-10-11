def test_save_layervariants_preservestail(self):
        test_file = self.get_test_data_path("layer-variants.psd")
        original_bytes = Path(test_file).read_bytes()
        output_file = self.get_persistent_artifact_path(
            "layer_variants_tail_test.psd"
        )

        with PsdImage.load(test_file) as image:
            image.layers[2].name = "Ellipse 1 Updated"
            image.save(output_file)
        self.log_artifact_directory(output_file)

        saved_bytes = Path(output_file).read_bytes()
        assert self.read_layer_and_mask_tail(saved_bytes) == self.read_layer_and_mask_tail(
            original_bytes
        )