def test_save_changesbounds(self):
        test_file = self.get_test_data_path("test.psd")

        output_file = self.get_persistent_artifact_path("layer_bounds_test.psd")

        with PsdImage.load(test_file) as image:
            new_bounds = Rectangle.from_left_top_right_bottom(10, 20, 40, 60)
            image.layers[0].left = new_bounds.left
            image.layers[0].top = new_bounds.top
            image.layers[0].right = new_bounds.right
            image.layers[0].bottom = new_bounds.bottom
            image.save(output_file)
        self.log_artifact_directory(output_file)

        with PsdImage.load(output_file) as reloaded:
            assert reloaded.layers[0].bounds == Rectangle(
                0, 0, new_bounds.width, new_bounds.height
            )
            assert reloaded.layers[0].left == new_bounds.left
            assert reloaded.layers[0].top == new_bounds.top
            assert reloaded.layers[0].right == new_bounds.right
            assert reloaded.layers[0].bottom == new_bounds.bottom