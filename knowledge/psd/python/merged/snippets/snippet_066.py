def test_save_roundtrip_loads_again(self):
        test_file = os.path.join(os.path.dirname(__file__), "testdata", "test.psd")
        output_file = self.get_persistent_artifact_path("roundtrip_test.psd")

        # Keep the original image alive for later assertions
        image1 = PsdImage.load(test_file)
        original_length = len(image1.layers)
        original_layer_name = image1.layers[0].name if original_length > 0 else ""

        image1.save(output_file)
        self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as image2:
            assert image2.width == image1.width
            assert image2.height == image1.height
            assert image2.channels == image1.channels
            assert image2.bits_per_channel == image1.bits_per_channel
            assert len(image2.layers) == original_length
            if len(image2.layers) > 0:
                assert image2.layers[0].name == original_layer_name

        # Dispose the original image if a close/dispose method exists
        if hasattr(image1, "close"):
            image1.close()
        elif hasattr(image1, "Dispose"):
            image1.Dispose()