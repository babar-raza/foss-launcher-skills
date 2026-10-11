def test_save_changesblendmode(self):
        test_file = self.get_test_data_path("test.psd")
        output_file = self.get_persistent_artifact_path("layer_blend_mode_test.psd")

        with PsdImage.load(test_file) as image:
            image.layers[0].blend_mode_key = BlendMode.MULTIPLY
            image.save(output_file)
        self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[0].blend_mode_key == BlendMode.MULTIPLY

        with open(test_file, "rb") as f:
            original_bytes = f.read()
        with open(output_file, "rb") as f:
            saved_bytes = f.read()
        assert self.read_layer_info_length(original_bytes) == self.read_layer_info_length(
            saved_bytes
        )