def test_string_values(self):
        """Test setting and saving string values."""
        test_values = [
            "Hello World",
            "Test String",
            "123",  # String representation of number
            "3.14",  # String representation of float
            "",  # Empty string
            "Special chars: !@#$%^&*()",
            "Unicode: 你好世界",
            "Multi\nline\nstring"
        ]
        
        for i, value in enumerate(test_values):
            cell = Cell(value)
            self.worksheet.cells[f"C{i+1}"] = cell
            
            # Verify the value was set correctly
            self.assertEqual(self.worksheet.cells[f"C{i+1}"].value, value)
            self.assertIsInstance(self.worksheet.cells[f"C{i+1}"].value, str)