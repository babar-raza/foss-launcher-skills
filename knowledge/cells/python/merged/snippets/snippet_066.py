def test_icon_set(self):
        """Test icon set rules."""
        print("Testing icon set rules...")
        
        # Test icon set rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'iconSet'
        cf1.icon_set_type = '3TrafficLights1'
        cf1.range = 'A1:A10'
        self.assertEqual(cf1.type, 'iconSet')
        self.assertEqual(cf1.icon_set_type, '3TrafficLights1')
        self.assertEqual(cf1.range, 'A1:A10')
        print(" Icon set created")
        
        # Add test data
        for i in range(1, 11):
            self.worksheet.cells[f'A{i}'].value = i * 10
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_icon_set.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Icon set test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")