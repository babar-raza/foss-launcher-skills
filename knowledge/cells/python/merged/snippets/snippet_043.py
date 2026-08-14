def test_mixed_values(self):
        """Test setting mixed value types in the same worksheet."""
        # Set up mixed values
        self.worksheet.cells["A1"] = Cell(42)  # int
        self.worksheet.cells["A2"] = Cell(3.14159)  # float
        self.worksheet.cells["A3"] = Cell("Hello")  # string
        self.worksheet.cells["A4"] = Cell(None, "=SUM(A1:A2)")  # formula
        
        # Verify all values are set correctly
        self.assertEqual(self.worksheet.cells["A1"].value, 42)
        self.assertIsInstance(self.worksheet.cells["A1"].value, int)
        
        self.assertEqual(self.worksheet.cells["A2"].value, 3.14159)
        self.assertIsInstance(self.worksheet.cells["A2"].value, float)
        
        self.assertEqual(self.worksheet.cells["A3"].value, "Hello")
        self.assertIsInstance(self.worksheet.cells["A3"].value, str)
        
        self.assertEqual(self.worksheet.cells["A4"].formula, "=SUM(A1:A2)")
        self.assertIsNone(self.worksheet.cells["A4"].value)