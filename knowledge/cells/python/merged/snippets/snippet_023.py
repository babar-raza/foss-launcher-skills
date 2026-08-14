def test_remove_auto_filter_persistence(self):
        """Test that removing auto filter is persisted correctly."""
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
        
        # Remove auto filter
        ws.auto_filter.remove()
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_remove_auto_filter.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify auto filter is removed
        self.assertIsNone(ws2.auto_filter.range)
        self.assertEqual(ws2.auto_filter.filter_columns, {})