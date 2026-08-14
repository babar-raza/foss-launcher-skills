def test_format_detection(self):
        self.assertEqual(self.format.extension, '3mf')
        self.assertIn('3mf', self.format.extensions)
        self.assertTrue(self.format.can_import)
        self.assertTrue(self.format.can_export)