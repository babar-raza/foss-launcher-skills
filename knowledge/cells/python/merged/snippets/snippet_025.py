def test_set_range_with_indices_persistence(self):
        """Test that setting range with indices is persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Age"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 30
        
        # Set auto filter range using indices
        ws.auto_filter.set_range(1, 1, 2, 2)
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_set_range_with_indices.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify range
        self.assertEqual(ws2.auto_filter.range, "A1:B2")