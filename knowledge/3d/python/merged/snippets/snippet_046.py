def test_save_options_creation(self):
        options = SaveOptions()
        self.assertIsNotNone(options)
        self.assertFalse(options.export_textures)