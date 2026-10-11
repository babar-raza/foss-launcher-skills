def test_save_changesclipping(self):
        test_file = self.get_test_data_path("test.psd")

        output_file = self.get_persistent_artifact_path("layer_clipping_test.psd")
        with open(test_file, "rb") as f:
            original_bytes = f.read()

        with PsdImage.load(test_file) as image:
            image.layers[0].clipping = 1
            image.save(output_file)
        self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[0].clipping == 1

        with open(output_file, "rb") as f:
            saved_bytes = f.read()
        assert self.read_layer_and_mask_tail(original_bytes) == self.read_layer_and_mask_tail(
            saved_bytes
        )