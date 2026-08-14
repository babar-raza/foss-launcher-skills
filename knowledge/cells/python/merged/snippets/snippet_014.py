def test_custom_filter_persistence(self):
        """Test that custom filters are persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Age"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 30
        ws.cells['A3'].value = "Bob"
        ws.cells['B3'].value = 25
        ws.cells['A4'].value = "Charlie"
        ws.cells['B4'].value = 35
        
        # Set auto filter range and apply custom filter
        ws.auto_filter.range = "A1:B4"
        ws.auto_filter.custom_filter(1, 'greaterThan', 25)
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_custom_filter.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify custom filter
        self.assertIn(1, ws2.auto_filter.filter_columns)
        filter_col = ws2.auto_filter.filter_columns[1]
        self.assertEqual(len(filter_col.custom_filters), 1)
        self.assertEqual(filter_col.custom_filters[0], ('greaterThan', '25'))