def test_dynamic_filter_persistence(self):
        """Test that dynamic filters are persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Date"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = "2024-01-15"
        ws.cells['A3'].value = "Bob"
        ws.cells['B3'].value = "2024-01-10"
        
        # Set auto filter range and apply dynamic filter
        ws.auto_filter.range = "A1:B3"
        ws.auto_filter.filter_dynamic(1, 'aboveAverage')
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_dynamic_filter.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify dynamic filter
        self.assertIn(1, ws2.auto_filter.filter_columns)
        filter_col = ws2.auto_filter.filter_columns[1]
        self.assertIsNotNone(filter_col.dynamic_filter)
        self.assertEqual(filter_col.dynamic_filter['type'], 'aboveAverage')