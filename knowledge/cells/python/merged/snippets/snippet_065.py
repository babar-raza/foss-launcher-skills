def test_data_bar(self):
        """Test data bar rules."""
        print("Testing data bar rules...")
        
        # Test data bar rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'dataBar'
        cf1.bar_color = 'FF006100'
        cf1.negative_color = 'FFFF0000'
        cf1.show_border = True
        cf1.direction = 'left-to-right'
        cf1.range = 'A1:A10'
        self.assertEqual(cf1.type, 'dataBar')
        self.assertEqual(cf1.bar_color, 'FF006100')
        self.assertEqual(cf1.negative_color, 'FFFF0000')
        self.assertTrue(cf1.show_border)
        self.assertEqual(cf1.direction, 'left-to-right')
        self.assertEqual(cf1.range, 'A1:A10')
        print(" Data bar created")
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 10
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_data_bar.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Data bar test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")