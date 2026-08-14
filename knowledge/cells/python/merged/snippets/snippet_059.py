def test_text_rules(self):
        """Test text rules (contains, does not contain, begins with, ends with)."""
        print("Testing text rules...")
        
        # Test contains rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'text'
        cf1.text_operator = 'contains'
        cf1.text_formula = 'error'
        cf1.range = 'A1:A10'
        cf1.font.color = 'FFFF0000'
        cf1.fill.set_solid_fill('FFFF00')
        self.assertEqual(cf1.type, 'text')
        self.assertEqual(cf1.text_operator, 'contains')
        self.assertEqual(cf1.text_formula, 'error')
        self.assertEqual(cf1.range, 'A1:A10')
        self.assertEqual(cf1.font.color, 'FFFF0000')
        self.assertEqual(cf1.fill.foreground_color, 'FFFF00')
        print(" Contains rule created")
        
        # Test does not contain rule
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'text'
        cf2.text_operator = 'notContains'
        cf2.text_formula = 'warning'
        cf2.range = 'B1:B10'
        cf2.font.color = 'FF00FF00'
        cf2.fill.set_solid_fill('FFFFFF00')
        self.assertEqual(cf2.type, 'text')
        self.assertEqual(cf2.text_operator, 'notContains')
        self.assertEqual(cf2.text_formula, 'warning')
        self.assertEqual(cf2.range, 'B1:B10')
        self.assertEqual(cf2.font.color, 'FF00FF00')
        self.assertEqual(cf2.fill.foreground_color, 'FFFFFF00')
        print(" Does not contain rule created")
        
        # Test begins with rule
        cf3 = self.worksheet.conditional_formats.add()
        cf3.type = 'text'
        cf3.text_operator = 'beginsWith'
        cf3.text_formula = 'prefix'
        cf3.range = 'C1:C10'
        cf3.font.bold = True
        self.assertEqual(cf3.type, 'text')
        self.assertEqual(cf3.text_operator, 'beginsWith')
        self.assertEqual(cf3.text_formula, 'prefix')
        self.assertEqual(cf3.range, 'C1:C10')
        self.assertTrue(cf3.font.bold)
        print(" Begins with rule created")
        
        # Test ends with rule
        cf4 = self.worksheet.conditional_formats.add()
        cf4.type = 'text'
        cf4.text_operator = 'endsWith'
        cf4.text_formula = 'suffix'
        cf4.range = 'D1:D10'
        cf4.font.italic = True
        self.assertEqual(cf4.type, 'text')
        self.assertEqual(cf4.text_operator, 'endsWith')
        self.assertEqual(cf4.text_formula, 'suffix')
        self.assertEqual(cf4.range, 'D1:D10')
        self.assertTrue(cf4.font.italic)
        print(" Ends with rule created")
        
        # Add test data for text rules
        # Column A: Contains "error" - should trigger for cells with "error"
        self.worksheet.cells['A1'].value = "error message"
        self.worksheet.cells['A2'].value = "warning message"
        self.worksheet.cells['A3'].value = "error found"
        self.worksheet.cells['A4'].value = "info message"
        self.worksheet.cells['A5'].value = "error detected"
        self.worksheet.cells['A6'].value = "success"
        self.worksheet.cells['A7'].value = "error"
        self.worksheet.cells['A8'].value = "warning"
        self.worksheet.cells['A9'].value = "critical error"
        self.worksheet.cells['A10'].value = "normal"
        
        # Column B: Does not contain "warning" - should trigger for cells without "warning"
        self.worksheet.cells['B1'].value = "error message"
        self.worksheet.cells['B2'].value = "success message"
        self.worksheet.cells['B3'].value = "info message"
        self.worksheet.cells['B4'].value = "warning message"
        self.worksheet.cells['B5'].value = "critical error"
        self.worksheet.cells['B6'].value = "normal"
        self.worksheet.cells['B7'].value = "error"
        self.worksheet.cells['B8'].value = "warning"
        self.worksheet.cells['B9'].value = "critical error"
        self.worksheet.cells['B10'].value = "normal"
        
        # Column C: Begins with "prefix" - should trigger for cells starting with "prefix"
        self.worksheet.cells['C1'].value = "prefix_test"
        self.worksheet.cells['C2'].value = "other_text"
        self.worksheet.cells['C3'].value = "prefix_data"
        self.worksheet.cells['C4'].value = "prefix_value"
        self.worksheet.cells['C5'].value = "different"
        self.worksheet.cells['C6'].value = "prefix_item"
        self.worksheet.cells['C7'].value = "prefix_string"
        self.worksheet.cells['C8'].value = "another_text"
        self.worksheet.cells['C9'].value = "prefix_test_again"
        self.worksheet.cells['C10'].value = "no_prefix"
        
        # Column D: Ends with "suffix" - should trigger for cells ending with "suffix"
        self.worksheet.cells['D1'].value = "test_suffix"
        self.worksheet.cells['D2'].value = "suffix_data"
        self.worksheet.cells['D3'].value = "suffix_value"
        self.worksheet.cells['D4']