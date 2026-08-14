def test_file_format_create_options(self):
        file_format = FileFormat()
        load_options = file_format.create_load_options()
        save_options = file_format.create_save_options()
        
        self.assertIsInstance(load_options, LoadOptions)
        self.assertIsInstance(save_options, SaveOptions)
        self.assertEqual(load_options.file_format, file_format)
        self.assertEqual(save_options.file_format, file_format)