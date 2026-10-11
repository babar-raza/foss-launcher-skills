def test_load_options_properties(self):
        options = ObjLoadOptions()
        
        self.assertFalse(options.flip_coordinate_system)
        self.assertTrue(options.enable_materials)
        self.assertAlmostEqual(options.scale, 1.0)
        self.assertTrue(options.normalize_normal)
        
        options.flip_coordinate_system = True
        options.enable_materials = False
        options.scale = 2.5
        options.normalize_normal = False
        
        self.assertTrue(options.flip_coordinate_system)
        self.assertFalse(options.enable_materials)
        self.assertAlmostEqual(options.scale, 2.5)
        self.assertFalse(options.normalize_normal)