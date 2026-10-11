def test_comment_api_methods(self):
        """Test all comment API methods."""
        # Test set_comment
        cell = Cell("Test")
        cell.set_comment("Comment text", "Author")
        self.assertEqual(cell.get_comment()['text'], "Comment text")
        self.assertEqual(cell.get_comment()['author'], "Author")
        
        # Test get_comment
        comment = cell.get_comment()
        self.assertIsInstance(comment, dict)
        self.assertIn('text', comment)
        self.assertIn('author', comment)
        
        # Test clear_comment
        cell.clear_comment()
        self.assertIsNone(cell.get_comment())