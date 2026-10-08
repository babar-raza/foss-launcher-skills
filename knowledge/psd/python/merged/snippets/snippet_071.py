def test_save_mutation_preserves_flags(self):
        test_file = os.path.join(os.path.dirname(__file__), "testdata", "test.psd")
        output_file = self.get_persistent_artifact_path("preserve_flags_and_blend.psd")

        with PsdImage.load(test_file) as image:
            image.layers[0].name = "Renamed"
            image.save(output_file)
            self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[0].raw_blend_mode_key == "norm"
            assert reloaded.layers[0].IsVisible is True