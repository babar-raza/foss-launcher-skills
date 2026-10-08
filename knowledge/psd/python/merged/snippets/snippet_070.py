def test_save_changes_layer_opacity(self):
        test_file = os.path.join(os.path.dirname(__file__), "testdata", "test.psd")
        output_file = self.get_persistent_artifact_path("layer_opacity_test.psd")

        with PsdImage.load(test_file) as image:
            assert len(image.layers) > 0

            original_opacity = image.layers[0].opacity
            new_opacity = max(0, original_opacity - 50)
            image.layers[0].opacity = new_opacity

            image.save(output_file)
            self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[0].opacity == new_opacity