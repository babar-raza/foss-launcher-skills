def test_save_changes_layer_name(self):
        test_file = os.path.join(os.path.dirname(__file__), "testdata", "test.psd")
        output_file = self.get_persistent_artifact_path("layer_name_test.psd")

        with PsdImage.load(test_file) as image:
            assert len(image.layers) > 0

            original_name = image.layers[0].name
            image.layers[0].name = "Test Layer name"

            image.save(output_file)
            self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[0].name == "Test Layer name"