def test_load_conditional_formatting(self):
        """Test loading conditional formatting from xlsx file."""
        print("Testing load conditional formatting...")
        
        # First, save a workbook with conditional formatting
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'cellValue'
        cf1.operator = 'greaterThan'
        cf1.formula1 = '100'
        cf1.range = 'A1:A10'
        cf1.font.bold = True
        cf1.font.color = 'FFFF0000'
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 10
            self.worksheet.cells[f'B{i}'].value = i * 100
        
        # Save workbook
        save_path = examples_output_path('example_test_conditional_formatting_cell_value.xlsx')
        self.workbook.save(save_path)
        
        # Load workbook back
        loaded_workbook = Workbook(save_path)
        loaded_ws = loaded_workbook.worksheets[0]
        
        # Verify conditional formatting was loaded
        self.assertTrue(hasattr(loaded_ws, 'conditional_formats'))
        self.assertEqual(len(loaded_ws.conditional_formats._formats), 1)
        
        # Verify conditional format properties
        # Note: Excel uses 'cellIs' as the XML type name for cell value rules,
        # but the API always returns 'cellValue' to users for consistency
        loaded_cf = loaded_ws.conditional_formats._formats[0]
        self.assertEqual(loaded_cf.type, 'cellValue')
        self.assertEqual(loaded_cf.operator, 'greaterThan')
        self.assertEqual(loaded_cf.formula1, '100')
        self.assertEqual(loaded_cf.range, 'A1:A10')
        self.assertTrue(loaded_cf.font.bold)
        self.assertEqual(loaded_cf.font.color, 'FFFF0000')
        
        print(f" Loaded conditional formatting from {save_path}")