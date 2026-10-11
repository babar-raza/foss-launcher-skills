def test_integer_values(self):
        """Test setting and saving integer values."""
        test_values = [0, 1, -1, 42, 1000, -999]
        
        for i, value in enumerate(test_values):
            cell = Cell(value)
            self.worksheet.cells[f"A{i+1}"] = cell
            
            # Verify the value was set correctly
            self.assertEqual(self.worksheet.cells[f"A{i+1}"].value, value)
            self.assertIsInstance(self.worksheet.cells[f"A{i+1}"].value, int)