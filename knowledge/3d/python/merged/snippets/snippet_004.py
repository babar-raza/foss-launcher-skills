def test_load_options(self):
        options = self.plugin.create_load_options()
        self.assertIsInstance(options, ThreeMfLoadOptions)
        self.assertFalse(options.flip_coordinate_system)
        
        options.flip_coordinate_system = True
        self.assertTrue(options.flip_coordinate_system)