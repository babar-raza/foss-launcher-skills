def test_save_options(self):
        options = self.plugin.create_save_options()
        self.assertIsInstance(options, ThreeMfSaveOptions)
        self.assertTrue(options.enable_compression)
        self.assertTrue(options.build_all)
        self.assertFalse(options.flip_coordinate_system)
        
        options.enable_compression = False
        self.assertFalse(options.enable_compression)
        
        options.flip_coordinate_system = True
        self.assertTrue(options.flip_coordinate_system)