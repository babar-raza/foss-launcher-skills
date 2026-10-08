def test_save_layeredpsb_changesblendmode(self):
        test_file = self.get_test_data_path("layered.psb")
        output_file = self.get_persistent_artifact_path(
            "layered_psb_blend_mode_test.psb"
        )

        with PsdImage.load(test_file) as image:
            image.layers[1].blend_mode_key = BlendMode.MULTIPLY
            image.save(output_file)
        self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[1].blend_mode_key == BlendMode.MULTIPLY