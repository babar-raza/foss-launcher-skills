def test_collada_load_options(self):
        options = ColladaLoadOptions()

        self.assertEqual(options.flip_coordinate_system, False)

        options.flip_coordinate_system = True
        self.assertEqual(options.flip_coordinate_system, True)