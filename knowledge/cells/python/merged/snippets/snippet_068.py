def test_save_conditional_formatting(self):
        """Test saving conditional formatting to xlsx file."""
        print("Testing save conditional formatting...")
        
        # Create multiple conditional formats
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'cellValue'
        cf1.operator = 'lessThan'
        cf1.formula1 = '100'
        cf1.range = 'A1:A10'
        cf1.font.bold = True
        cf1.font.color = 'FFFF0000'
        
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'cellValue'
        cf2.operator = 'greaterThan'
        cf2.formula1 = '50'
        cf2.range = 'B1:B10'
        cf2.fill.set_solid_fill('FFFFFF00')
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 10
            self.worksheet.cells[f'B{i}'].value = i * 100
        
        # Ensure outputfiles directory exists
        os.makedirs('outputfiles', exist_ok=True)
        
        # Save workbook
        output_path = examples_output_path('example_test_conditional_formatting_cell_value.xlsx')
        self.workbook.save(output_path)
        
        # Verify file was created
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f" Saved to {output_path} ({file_size} bytes)")