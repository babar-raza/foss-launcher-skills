def test_duplicate_unique_values(self):
        """Test duplicate/unique values rules."""
        print("Testing duplicate/unique values rules...")
        
        # Test duplicate values rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'duplicateValues'
        cf1.duplicate = True
        cf1.range = 'A1:A10'
        cf1.fill.set_solid_fill('FFFF0000')
        self.assertEqual(cf1.type, 'duplicateValues')
        self.assertTrue(cf1.duplicate)
        self.assertEqual(cf1.range, 'A1:A10')
        self.assertEqual(cf1.fill.foreground_color, 'FFFF0000')
        print(" Duplicate values rule created")
        
        # Test unique values rule
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'uniqueValues'
        cf2.duplicate = False
        cf2.range = 'B1:B10'
        cf2.fill.set_solid_fill('00FF00')
        self.assertEqual(cf2.type, 'uniqueValues')
        self.assertFalse(cf2.duplicate)
        self.assertEqual(cf2.range, 'B1:B10')
        self.assertEqual(cf2.fill.foreground_color, '00FF00')
        print(" Unique values rule created")
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i if i <= 5 else i - 5
            self.worksheet.cells[f'B{i}'].value = i * 100
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_duplicate_unique_values.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Duplicate/unique values test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")