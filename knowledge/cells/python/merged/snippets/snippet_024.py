def test_numeric_value_filter_persistence(self):
        """Test that numeric value filters are persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "ID"
        ws.cells['B1'].value = "Score"
        ws.cells['A2'].value = 1
        ws.cells['B2'].value = 95
        ws.cells['A3'].value = 2
        ws.cells['B3'].value = 87
        
        # Set auto filter range and apply numeric filter
        ws.auto_filter.range = "A1:B3"
        ws.auto_filter.filter(0, [1, 2])
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_numeric_value_filter.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify numeric filter
        self.assertIn(0, ws2.auto_filter.filter_columns)
        filter_col = ws2.auto_filter.filter_columns[0]
        self.assertEqual(len(filter_col.filters), 2)
        self.assertIn("1", filter_col.filters)
        self.assertIn("2", filter_col.filters)