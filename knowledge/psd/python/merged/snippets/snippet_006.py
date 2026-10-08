def test_image_setters_updatemetadata(self):
        with Image.load(self.get_test_data_path("test.psd")) as img:
            psd_image = img
            layers = psd_image.layers
            version = psd_image.version

            psd_image.color_mode = ColorModes.RGB
            psd_image.layers = layers
            psd_image.global_angle = 45
            psd_image.version = version

            assert psd_image.color_mode == ColorModes.RGB
            assert len(psd_image.layers) == len(layers)
            assert psd_image.global_angle == 45
            assert psd_image.version == version