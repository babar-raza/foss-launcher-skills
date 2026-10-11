def test_alignment_edge_cases(self):
        """Test edge cases for alignment settings."""
        # Test invalid horizontal alignment
        with self.assertRaises(ValueError):
            cell = Cell("Test")
            cell.style.set_horizontal_alignment('invalid')
        
        # Test invalid vertical alignment
        with self.assertRaises(ValueError):
            cell = Cell("Test")
            cell.style.set_vertical_alignment('invalid')
        
        # Test invalid text rotation
        with self.assertRaises(ValueError):
            cell = Cell("Test")
            cell.style.set_text_rotation(200)  # Not in 0-180 or 255 range
        
        # Test invalid reading order
        with self.assertRaises(ValueError):
            cell = Cell("Test")
            cell.style.set_reading_order(5)  # Not 0, 1, or 2
        
        # Test negative indent (should be set to 0)
        cell = Cell("Test")
        cell.style.set_indent(-5)
        self.assertEqual(cell.style.alignment.indent, 0)