def test_formula_rule(self):
        """Test formula-based rules."""
        print("Testing formula-based rules...")
        
        # Test formula rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'formula'
        cf1.formula = '=A1>100'
        cf1.range = 'A1:A10'
        cf1.font.bold = True
        cf1.font.color = 'FFFF0000'
        self.assertEqual(cf1.type, 'formula')
        self.assertEqual(cf1.formula, '=A1>100')
        self.assertEqual(cf1.range, 'A1:A10')
        self.assertTrue(cf1.font.bold)
        self.assertEqual(cf1.font.color, 'FFFF0000')
        print(" Formula rule created")
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 10
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_formula_rule.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Formula rule test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")