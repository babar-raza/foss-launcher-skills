def test_shrink_to_fit(self):
        """Test shrink to fit setting."""
        # Test shrink to fit enabled
        cell1 = Cell("Shrink to Fit Enabled")
        cell1.style.set_shrink_to_fit(True)
        self.worksheet.cells["D1"] = cell1
        self.assertTrue(self.worksheet.cells["D1"].style.alignment.shrink_to_fit)
        
        # Test shrink to fit disabled
        cell2 = Cell("Shrink to Fit Disabled")
        cell2.style.set_shrink_to_fit(False)
        self.worksheet.cells["D2"] = cell2
        self.assertFalse(self.worksheet.cells["D2"].style.alignment.shrink_to_fit)