def test_value_filter_persistence(self):
        """Test that value filters are persisted correctly."""
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
        
        # Set auto filter range and apply value filter
        ws.auto_filter.range = "A1:B4"
        ws.auto_filter.filter(0, ["Alice", "Charlie"])
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_value_filter.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify filter
        self.assertEqual(ws2.auto_filter.range, "A1:B4")
        self.assertIn(0, ws2.auto_filter.filter_columns)
        filter_col = ws2.auto_filter.filter_columns[0]
        self.assertEqual(len(filter_col.filters), 2)
        self.assertIn("Alice", filter_col.filters)
        self.assertIn("Charlie", filter_col.filters)