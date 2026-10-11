def test_multiple_columns_filter_persistence(self):
        """Test that filters on multiple columns are persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Age"
        ws.cells['C1'].value = "City"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 30
        ws.cells['C2'].value = "New York"
        ws.cells['A3'].value = "Bob"
        ws.cells['B3'].value = 25
        ws.cells['C3'].value = "London"
        
        # Set auto filter range and apply filters to multiple columns
        ws.auto_filter.range = "A1:C3"
        ws.auto_filter.filter(0, ["Alice"])
        ws.auto_filter.custom_filter(1, 'greaterThan', 25)
        ws.auto_filter.filter(2, ["New York"])
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_multiple_columns_filter.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify all filters
        self.assertIn(0, ws2.auto_filter.filter_columns)
        self.assertIn(1, ws2.auto_filter.filter_columns)
        self.assertIn(2, ws2.auto_filter.filter_columns)
        
        # Column 0: value filter
        filter_col_0 = ws2.auto_filter.filter_columns[0]
        self.assertEqual(len(filter_col_0.filters), 1)
        self.assertIn("Alice", filter_col_0.filters)
        
        # Column 1: custom filter
        filter_col_1 = ws2.auto_filter.filter_columns[1]
        self.assertEqual(len(filter_col_1.custom_filters), 1)
        self.assertEqual(filter_col_1.custom_filters[0], ('greaterThan', '25'))
        
        # Column 2: value filter
        filter_col_2 = ws2.auto_filter.filter_columns[2]
        self.assertEqual(len(filter_col_2.filters), 1)
        self.assertIn("New York", filter_col_2.filters)