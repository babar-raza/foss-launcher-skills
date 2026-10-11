def test_save_resources_preserves_raw(self):
        test_file = pathlib.Path(self.get_test_data_path("test.psd")) #pathlib.Path(self.test_context.current_dir) / "testdata" / "test.psd"
        original_bytes = test_file.read_bytes()
        output_file = pathlib.Path(
            self.get_persistent_artifact_path("resources_roundtrip_test.psd")
        )

        image = PsdImage.load(str(test_file))
        image.save(str(output_file))
        self.log_artifact_directory(str(output_file))

        saved_bytes = output_file.read_bytes()
        original_section = self.extract_image_resources_section(original_bytes)
        saved_section = self.extract_image_resources_section(saved_bytes)

        assert saved_section == original_section

        reloaded = PsdImage.load(str(output_file))
        assert reloaded.has_image_resources is True
        assert reloaded.resource_count == 26