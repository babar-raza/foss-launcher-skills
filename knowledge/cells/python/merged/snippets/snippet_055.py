def test_clear_comments(self):
        """Test clearing comments from cells."""
        # Create a cell with a comment
        cell = Cell("Test Cell")
        cell.set_comment("This is a comment", "Author")
        self.worksheet.cells["A1"] = cell
        
        # Verify comment exists
        self.assertIsNotNone(self.worksheet.cells["A1"].get_comment())
        
        # Clear the comment
        self.worksheet.cells["A1"].clear_comment()
        
        # Verify comment is cleared
        self.assertIsNone(self.worksheet.cells["A1"].get_comment())