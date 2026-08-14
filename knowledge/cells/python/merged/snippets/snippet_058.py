def test_cell_value_rules(self):
        """Test cell value rules (greater than, less than, between, equal to)."""
        print("Testing cell value rules...")
        
        # Test greater than rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'cellValue'
        cf1.operator = 'greaterThan'
        cf1.formula1 = '100'
        cf1.range = 'B1:B10'
        cf1.font.bold = True
        cf1.font.color = 'FFFF0000'
        self.assertEqual(cf1.type, 'cellValue')
        self.assertEqual(cf1.operator, 'greaterThan')
        self.assertEqual(cf1.formula1, '100')
        self.assertEqual(cf1.range, 'B1:B10')
        self.assertTrue(cf1.font.bold)
        self.assertEqual(cf1.font.color, 'FFFF0000')
        print("  Greater than rule created")
        
        # Test less than rule
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'cellValue'
        cf2.operator = 'lessThan'
        cf2.formula1 = '50'
        cf2.range = 'A1:A10'
        cf2.fill.set_solid_fill('FFFFFF00')
        self.assertEqual(cf2.type, 'cellValue')
        self.assertEqual(cf2.operator, 'lessThan')
        self.assertEqual(cf2.formula1, '50')
        self.assertEqual(cf2.range, 'A1:A10')
        self.assertEqual(cf2.fill.foreground_color, 'FFFFFF00')
        print("  Less than rule created")
        
        # Test between rule
        cf3 = self.worksheet.conditional_formats.add()
        cf3.type = 'cellValue'
        cf3.operator = 'between'
        cf3.formula1 = '10'
        cf3.formula2 = '100'
        cf3.range = 'C1:C10'
        cf3.font.italic = True
        cf3.font.color = 'FF0000FF'
        self.assertEqual(cf3.type, 'cellValue')
        self.assertEqual(cf3.operator, 'between')
        self.assertEqual(cf3.formula1, '10')
        self.assertEqual(cf3.formula2, '100')
        self.assertEqual(cf3.range, 'C1:C10')
        self.assertTrue(cf3.font.italic)
        self.assertEqual(cf3.font.color, 'FF0000FF')
        print("  Between rule created")
        
        # Test equal to rule
        cf4 = self.worksheet.conditional_formats.add()
        cf4.type = 'cellValue'
        cf4.operator = 'equal'
        cf4.formula1 = '75'
        cf4.range = 'D1:D10'
        cf4.font.underline = True
        self.assertEqual(cf4.type, 'cellValue')
        self.assertEqual(cf4.operator, 'equal')
        self.assertEqual(cf4.formula1, '75')
        self.assertEqual(cf4.range, 'D1:D10')
        self.assertTrue(cf4.font.underline)
        print("  Equal to rule created")
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 10
            self.worksheet.cells[f'B{i}'].value = i * 100
            self.worksheet.cells[f'C{i}'].value = 50 + (i * 10)
            self.worksheet.cells[f'D{i}'].value = i * 75
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_cell_value_rules.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Cell value rules test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")