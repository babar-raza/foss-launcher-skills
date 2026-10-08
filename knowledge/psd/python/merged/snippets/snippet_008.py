def test_save_officialmutation_persists(self):
        output_file = self.get_persistent_artifact_path(
            "official_style_layer_mutation.psd"
        )

        with Image.load(self.get_test_data_path("test.psd")) as img:
            psd_image = img
            layer = psd_image.layers[0]
            layer.name = "Official style"
            layer.left = 10
            layer.top = 20
            layer.right = 40
            layer.bottom = 60
            layer.blend_mode_key = BlendMode.MULTIPLY
            psd_image.save(output_file)

        with Image.load(output_file) as reloaded_img:
            reloaded = reloaded_img
            layer = reloaded.layers[0]
            assert layer.name == "Official style"
            assert layer.bounds == Rectangle(0, 0, 30, 40)
            assert layer.left == 10
            assert layer.top == 20
            assert layer.right == 40
            assert layer.bottom == 60
            assert layer.blend_mode_key == BlendMode.MULTIPLY