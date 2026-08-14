def test_filter_button_visibility_persistence(self):
        """Test that filter button visibility is persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Age"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 30
        
        # Set auto filter range and hide filter button for column 0
        ws.auto_filter.range = "A1:B2"
        ws.auto_filter.show_filter_button(0, False)
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_filter_button_visibility.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify filter button visibility
        self.assertIn(0, ws2.auto_filter.filter_columns)
        filter_col = ws2.auto_filter.filter_columns[0]
        self.assertFalse(filter_col.filter_button)