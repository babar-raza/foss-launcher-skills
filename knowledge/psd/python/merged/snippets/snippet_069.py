def test_save_changes_layer_visibility(self):
        test_file = os.path.join(os.path.dirname(__file__), "testdata", "test.psd")
        output_file = self.get_persistent_artifact_path("layer_visible_test.psd")

        with PsdImage.load(test_file) as image:
            assert len(image.layers) > 0

            original_visible = image.layers[0].IsVisible
            image.layers[0].is_visible = not original_visible

            image.save(output_file)
            self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[0].IsVisible == (not original_visible)