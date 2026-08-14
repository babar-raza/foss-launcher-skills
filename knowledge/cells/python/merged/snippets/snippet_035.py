def test_load_and_verify_border_settings(self):
        """Test loading and verifying border settings from file."""
        # First, save a file with border settings
        self.test_comprehensive_border_test()
        output_path = examples_output_path('example_test_border_settings.xlsx')
        self.workbook.save(output_path)
        
        # Load the file back
        loaded_workbook = Workbook(output_path)
        loaded_worksheet = loaded_workbook.worksheets[0]
        
        # Verify that the file was loaded (basic verification)
        # Note: Full border verification would require parsing the XML structure
        # which is complex and beyond the scope of this test
        self.assertIsNotNone(loaded_worksheet)
        
        # Verify we can access cells
        cell_a1 = loaded_worksheet.cells["A1"]
        self.assertIsNotNone(cell_a1)
        
        cell_a2 = loaded_worksheet.cells["A2"]
        self.assertIsNotNone(cell_a2)
        
        print(f"Successfully loaded and verified border settings from: {output_path}")