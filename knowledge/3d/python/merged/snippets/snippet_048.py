def test_save_options_properties(self):
        options = SaveOptions()
        options.export_textures = True
        
        self.assertTrue(options.export_textures)