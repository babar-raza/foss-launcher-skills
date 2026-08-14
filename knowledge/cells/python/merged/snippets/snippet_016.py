def test_top10_filter_persistence(self):
        """Test that top10 filters are persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Score"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 95
        ws.cells['A3'].value = "Bob"
        ws.cells['B3'].value = 87
        ws.cells['A4'].value = "Charlie"
        ws.cells['B4'].value = 92
        
        # Set auto filter range and apply top10 filter
        ws.auto_filter.range = "A1:B4"
        ws.auto_filter.filter_top10(1, top=True, percent=False, val=3)
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_top10_filter.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify top10 filter
        self.assertIn(1, ws2.auto_filter.filter_columns)
        filter_col = ws2.auto_filter.filter_columns[1]
        self.assertIsNotNone(filter_col.top10_filter)
        self.assertTrue(filter_col.top10_filter['top'])
        self.assertFalse(filter_col.top10_filter['percent'])
        self.assertEqual(filter_col.top10_filter['val'], 3)