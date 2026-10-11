def test_load_options_creation(self):
        options = LoadOptions()
        self.assertIsNotNone(options)
        self.assertIsNone(options.encoding)
        self.assertIsNone(options.file_name)
        self.assertEqual(options.lookup_paths, [])