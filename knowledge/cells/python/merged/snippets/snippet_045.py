def test_edge_cases(self):
        """Test edge cases for cell values."""
        # Test None value
        cell = Cell(None)
        self.assertIsNone(cell.value)
        self.assertIsNone(cell.formula)
        
        # Test empty string
        cell = Cell("")
        self.assertEqual(cell.value, "")
        self.assertIsInstance(cell.value, str)
        
        # Test very large numbers
        cell = Cell(999999999999)
        self.assertEqual(cell.value, 999999999999)
        
        # Test very small decimals
        cell = Cell(0.0000001)
        self.assertEqual(cell.value, 0.0000001)
        
        # Test scientific notation
        cell = Cell(1.23e-10)
        self.assertEqual(cell.value, 1.23e-10)