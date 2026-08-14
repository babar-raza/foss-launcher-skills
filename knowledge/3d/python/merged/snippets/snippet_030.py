def test_collada_save_options(self):
        options = ColladaSaveOptions()

        self.assertEqual(options.flip_coordinate_system, False)
        self.assertEqual(options.enable_materials, True)
        self.assertEqual(options.indented, True)

        options.flip_coordinate_system = True
        self.assertEqual(options.flip_coordinate_system, True)

        options.indented = False
        self.assertEqual(options.indented, False)