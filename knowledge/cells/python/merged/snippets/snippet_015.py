def test_color_filter_persistence(self):
        """Test that color filters are persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Age"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 30
        ws.cells['A3'].value = "Bob"
        ws.cells['B3'].value = 25
        
        # Set auto filter range and apply color filter
        ws.auto_filter.range = "A1:B3"
        ws.auto_filter.filter_by_color(0, 'FFFF0000', True)
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_color_filter.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify color filter
        self.assertIn(0, ws2.auto_filter.filter_columns)
        filter_col = ws2.auto_filter.filter_columns[0]
        self.assertIsNotNone(filter_col.color_filter)
        self.assertEqual(filter_col.color_filter['color'], 'FFFF0000')
        self.assertTrue(filter_col.color_filter['cell_color'])