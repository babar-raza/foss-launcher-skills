def test_auto_filter_range_persistence(self):
        """Test that auto filter range is persisted correctly."""
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
        
        # Set auto filter range
        ws.auto_filter.range = "A1:C3"
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_auto_filter_range.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify auto filter range
        self.assertEqual(ws2.auto_filter.range, "A1:C3")