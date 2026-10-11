def test_save_resourcesfixture_raw(self):
        test_file = pathlib.Path(self.get_test_data_path("resources.psd"))
        original_bytes = test_file.read_bytes()
        output_file = pathlib.Path(
            self.get_persistent_artifact_path(
                "resources_fixture_roundtrip_test.psd"
            )
        )

        image = PsdImage.load(str(test_file))
        image.save(str(output_file))
        self.log_artifact_directory(str(output_file))

        saved_bytes = output_file.read_bytes()
        assert (
            self.extract_image_resources_section(saved_bytes)
            == self.extract_image_resources_section(original_bytes)
        )