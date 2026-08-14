def test_clear_filters_persistence(self):
        """Test that clearing filters is persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Age"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 30
        
        # Set auto filter range and apply filter
        ws.auto_filter.range = "A1:B2"
        ws.auto_filter.filter(0, ["Alice"])
        
        # Clear filters
        ws.auto_filter.clear_all_filters()
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_clear_filters.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify filters are cleared
        self.assertEqual(ws2.auto_filter.range, "A1:B2")
        self.assertEqual(ws2.auto_filter.filter_columns, {})