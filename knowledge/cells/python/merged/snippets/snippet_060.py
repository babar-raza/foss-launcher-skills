def test_date_rules(self):
        """Test date rules (yesterday, today, tomorrow, last 7 days, etc.)."""
        print("Testing date rules...")
        
        # Test yesterday rule
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'date'
        cf1.date_operator = 'yesterday'
        cf1.range = 'A1:A10'
        cf1.fill.set_solid_fill('FFFFFF00')
        self.assertEqual(cf1.type, 'date')
        self.assertEqual(cf1.date_operator, 'yesterday')
        self.assertEqual(cf1.range, 'A1:A10')
        self.assertEqual(cf1.fill.foreground_color, 'FFFFFF00')
        print(" Yesterday rule created")
        
        # Test today rule
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'date'
        cf2.date_operator = 'today'
        cf2.range = 'B1:B10'
        cf2.fill.set_solid_fill('FFFF00')
        self.assertEqual(cf2.type, 'date')
        self.assertEqual(cf2.date_operator, 'today')
        self.assertEqual(cf2.range, 'B1:B10')
        self.assertEqual(cf2.fill.foreground_color, 'FFFF00')
        print(" Today rule created")
        
        # Test tomorrow rule
        cf3 = self.worksheet.conditional_formats.add()
        cf3.type = 'date'
        cf3.date_operator = 'tomorrow'
        cf3.range = 'C1:C10'
        cf3.fill.set_solid_fill('00FF00')
        self.assertEqual(cf3.type, 'date')
        self.assertEqual(cf3.date_operator, 'tomorrow')
        self.assertEqual(cf3.range, 'C1:C10')
        self.assertEqual(cf3.fill.foreground_color, '00FF00')
        print(" Tomorrow rule created")
        
        # Test last 7 days rule
        cf4 = self.worksheet.conditional_formats.add()
        cf4.type = 'date'
        cf4.date_operator = 'last7Days'
        cf4.range = 'D1:D10'
        cf4.font.color = 'FF00FF00'
        self.assertEqual(cf4.type, 'date')
        self.assertEqual(cf4.date_operator, 'last7Days')
        self.assertEqual(cf4.range, 'D1:D10')
        self.assertEqual(cf4.font.color, 'FF00FF00')
        print(" Last 7 days rule created")
        
        # Add test data
        from datetime import datetime, timedelta
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        last_7_days = today - timedelta(days=7)
        for i, date in enumerate([yesterday, today, tomorrow, last_7_days], 1):
            self.worksheet.cells[f'A{i}'].value = date
            self.worksheet.cells[f'B{i}'].value = date
            self.worksheet.cells[f'C{i}'].value = date
            self.worksheet.cells[f'D{i}'].value = date
        
        # Save to separate file
        os.makedirs('outputfiles', exist_ok=True)
        output_path = examples_output_path('example_test_date_rules.xlsx')
        self.workbook.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"  Date rules test: {len(self.worksheet.conditional_formats._formats)} rules created")
        print(f"  Saved to {output_path} ({file_size} bytes)")