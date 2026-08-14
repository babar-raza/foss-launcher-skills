def test_above_below_average(self):
        """Test above/below average rules."""
        print("Testing above/below average rules...")
        
        # Test above average rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'aboveAverage'
        cf1.above = True
        cf1.range = 'A1:A10'
        cf1.fill.set_solid_fill('FFFFFF00')
        self.assertEqual(cf1.type, 'aboveAverage')
        self.assertTrue(cf1.above)
        self.assertEqual(cf1.range, 'A1:A10')
        self.assertEqual(cf1.fill.foreground_color, 'FFFFFF00')
        print(" Above average rule created")
        
        # Test below average rule
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'belowAverage'
        cf2.above = False
        cf2.range = 'B1:B10'
        cf2.fill.set_solid_fill('00FF00')
        self.assertEqual(cf2.type, 'belowAverage')
        self.assertFalse(cf2.above)
        self.assertEqual(cf2.range, 'B1:B10')
        self.assertEqual(cf2.fill.foreground_color, '00FF00')
        print("  Below average rule created")
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 100
            self.worksheet.cells[f'B{i}'].value = i * 100
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_above_below_average.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Above/below average test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")