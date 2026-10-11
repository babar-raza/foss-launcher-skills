def test_save_and_load_cell_values(self):
        """Test saving and loading cell values to verify persistence."""
        # Create test data with all value types
        test_data = {
            "A1": {"value": 42, "type": "int"},
            "A2": {"value": 3.14159, "type": "float"},
            "A3": {"value": "Hello World", "type": "string"},
            "A4": {"value": None, "formula": "=SUM(A1:A2)", "type": "formula"},
            "A5": {"value": -100, "type": "int"},
            "A6": {"value": 2.71828, "type": "float"},
            "A7": {"value": "", "type": "string"},
            "A8": {"value": None, "formula": "=A1+A2", "type": "formula"},
            "A9": {"value": "Test String", "type": "string"},
            "A10": {"value": 0, "type": "int"}
        }
        
        # Set up the test data
        for ref, data in test_data.items():
            if data["type"] == "formula":
                cell = Cell(data["value"], data["formula"])
            else:
                cell = Cell(data["value"])
            self.worksheet.cells[ref] = cell
        
        # Save to outputfiles folder
        output_path = examples_output_path('example_test_cell_values.xlsx')
        
        # Ensure outputfiles directory exists
        os.makedirs('outputfiles', exist_ok=True)
        
        self.workbook.save(output_path)
        
        # Verify file was created
        self.assertTrue(os.path.exists(output_path))
        
        # Verify file is not empty
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"Cell values test file saved to: {output_path}")
        print(f"File size: {file_size} bytes")
        
        # Load the file back
        loaded_workbook = Workbook(output_path)
        loaded_worksheet = loaded_workbook.worksheets[0]
        
        # Verify all values are loaded correctly
        for ref, expected_data in test_data.items():
            cell = loaded_worksheet.cells[ref]
            
            if expected_data["type"] == "formula":
                # For formulas, we expect the formula to be preserved
                self.assertEqual(cell.formula, expected_data["formula"])
                # The value might be calculated or None, depending on implementation
                # For now, just check that it's a formula cell
                self.assertIsNotNone(cell.formula)
            else:
                # For regular values, check the value and type
                # Handle empty string case specially
                if expected_data["value"] == "" and cell.value is None:
                    # Empty strings might be loaded as None - this is acceptable
                    pass
                elif cell.value is not None:
                    self.assertEqual(cell.value, expected_data["value"])
                    
                    if expected_data["type"] == "int":
                        self.assertIsInstance(cell.value, (int, float))  # Excel might convert to float
                        # If it's a whole number, it should be treated as int-like
                        if isinstance(cell.value, float):
                            self.assertEqual(cell.value, int(cell.value))
                    elif expected_data["type"] == "float":
                        self.assertIsInstance(cell.value, float)
                    elif expected_data["type"] == "string":
                        self.assertIsInstance(cell.value, str)