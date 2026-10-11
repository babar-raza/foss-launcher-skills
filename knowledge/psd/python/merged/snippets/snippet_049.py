def test_save_changescoordinates(self):
        test_file = self.get_test_data_path("test.psd")

        output_file = self.get_persistent_artifact_path("layer_coordinates_test.psd")

        with PsdImage.load(test_file) as image:
            layer = image.layers[0]
            layer.top = 10
            layer.left = 20
            layer.bottom = 30
            layer.right = 50
            image.save(output_file)
        self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[0].bounds == Rectangle(0, 0, 30, 20)
            assert reloaded.layers[0].left == 20
            assert reloaded.layers[0].top == 10
            assert reloaded.layers[0].right == 50
            assert reloaded.layers[0].bottom == 30