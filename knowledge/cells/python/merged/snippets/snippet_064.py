def test_color_scale(self):
        """Test color scale rules (2-color, 3-color)."""
        print("Testing color scale rules...")
        
        # Test 2-color scale
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'colorScale'
        cf1.color_scale_type = '2-color'
        cf1.min_color = 'FF63C384'
        cf1.max_color = 'FF006100'
        cf1.range = 'A1:A10'
        self.assertEqual(cf1.type, 'colorScale')
        self.assertEqual(cf1.color_scale_type, '2-color')
        self.assertEqual(cf1.min_color, 'FF63C384')
        self.assertEqual(cf1.max_color, 'FF006100')
        self.assertEqual(cf1.range, 'A1:A10')
        print("  2-color scale created")
        
        # Test 3-color scale
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'colorScale'
        cf2.color_scale_type = '3-color'
        cf2.min_color = 'FF63C384'
        cf2.mid_color = 'FFFFEB84'
        cf2.max_color = 'FF006100'
        cf2.range = 'B1:B10'
        self.assertEqual(cf2.type, 'colorScale')
        self.assertEqual(cf2.color_scale_type, '3-color')
        self.assertEqual(cf2.min_color, 'FF63C384')
        self.assertEqual(cf2.mid_color, 'FFFFEB84')
        self.assertEqual(cf2.max_color, 'FF006100')
        self.assertEqual(cf2.range, 'B1:B10')
        print("  3-color scale created")
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 10
            self.worksheet.cells[f'B{i}'].value = i * 100
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_color_scale.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Color scale test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")