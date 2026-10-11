def test_top_bottom_rules(self):
        """Test top/bottom rules (top 10 items, top 10%)."""
        print("Testing top/bottom rules...")
        
        # Test top 10 items rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'top10'
        cf1.top = True
        cf1.rank = 10
        cf1.range = 'A1:A10'
        cf1.fill.set_solid_fill('FFFF00')
        self.assertEqual(cf1.type, 'top10')
        self.assertTrue(cf1.top)
        self.assertEqual(cf1.rank, 10)
        self.assertEqual(cf1.range, 'A1:A10')
        self.assertEqual(cf1.fill.foreground_color, 'FFFF00')
        print(" Top 10 items rule created")
        
        # Test top 10% rule
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'top10'
        cf2.top = True
        cf2.percent = True
        cf2.rank = 10
        cf2.range = 'B1:B10'
        cf2.fill.set_solid_fill('00FF00')
        self.assertEqual(cf2.type, 'top10')
        self.assertTrue(cf2.top)
        self.assertTrue(cf2.percent)
        self.assertEqual(cf2.rank, 10)
        self.assertEqual(cf2.range, 'B1:B10')
        self.assertEqual(cf2.fill.foreground_color, '00FF00')
        print(" Top 10% rule created")
        
        # Test bottom 10 items rule
        cf3 = self.worksheet.conditional_formats.add()
        cf3.type = 'bottom10'
        cf3.top = False
        cf3.rank = 10
        cf3.range = 'C1:C10'
        cf3.fill.set_solid_fill('FFFFFF00')
        self.assertEqual(cf3.type, 'bottom10')
        self.assertFalse(cf3.top)
        self.assertEqual(cf3.rank, 10)
        self.assertEqual(cf3.range, 'C1:C10')
        self.assertEqual(cf3.fill.foreground_color, 'FFFFFF00')
        print(" Bottom 10 items rule created")
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 100
            self.worksheet.cells[f'B{i}'].value = i * 100
            self.worksheet.cells[f'C{i}'].value = i * 100
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_top_bottom_rules.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Top/bottom rules test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")