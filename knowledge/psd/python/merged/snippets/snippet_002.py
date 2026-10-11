def test_metadata_officialtypes_reads(self):
        with Image.load(self.get_test_data_path("test.psd")) as img:
            psd_image = img
            layer = psd_image.layers[0]

            bounds = layer.bounds
            blend_mode_key = layer.blend_mode_key

            assert bounds == Rectangle(0, 0, 100, 100)
            assert blend_mode_key == BlendMode.NORMAL
            assert layer.opacity == 255
            assert layer.is_visible is True