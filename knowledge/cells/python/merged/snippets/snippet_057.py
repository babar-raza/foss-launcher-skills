def test_comment_edge_cases(self):
        """Test edge cases for comments."""
        # Test comment on None value cell
        cell = Cell(None)
        cell.set_comment("Comment on None", "Author")
        self.assertIsNotNone(cell.get_comment())
        
        # Test empty comment text
        cell = Cell("Test")
        cell.set_comment("", "Author")
        comment = cell.get_comment()
        self.assertIsNotNone(comment)
        self.assertEqual(comment['text'], "")
        
        # Test None comment text (should handle gracefully)
        cell = Cell("Test")
        try:
            cell.set_comment(None, "Author")
            # If it doesn't raise an error, verify the result
            comment = cell.get_comment()
            self.assertIsNotNone(comment)
        except (TypeError, AttributeError):
            # Expected if None is not handled
            pass