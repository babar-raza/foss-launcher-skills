def test_load_options_properties(self):
        options = LoadOptions()
        options.encoding = 'utf-8'
        options.file_name = 'test.obj'
        options.lookup_paths = ['/path1', '/path2']
        
        self.assertEqual(options.encoding, 'utf-8')
        self.assertEqual(options.file_name, 'test.obj')
        self.assertEqual(options.lookup_paths, ['/path1', '/path2'])