def test_sort_state_persistence(self):
        """Test that sort state is persisted correctly."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Age"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 30
        ws.cells['A3'].value = "Bob"
        ws.cells['B3'].value = 25
        
        # Set auto filter range and sort
        ws.auto_filter.range = "A1:B3"
        ws.auto_filter.sort(1, True)
        
        # Save and reload
        test_file = os.path.join(self.output_dir, 'test_sort_state.xlsx')
        wb.save(test_file)
        wb2 = Workbook(test_file)
        ws2 = wb2.worksheets[0]
        
        # Verify sort state (using ECMA-376 compliant structure)
        self.assertIsNotNone(ws2.auto_filter.sort_state)
        self.assertEqual(ws2.auto_filter.sort_state['column_index'], 1)
        self.assertEqual(ws2.auto_filter.sort_state['descending'], False)