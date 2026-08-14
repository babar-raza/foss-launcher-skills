def test_border_copy(self):
        """Test border copying in style."""
        original_style = Style()
        original_style.set_border('all', line_style='medium', color='FF0000FF', weight=2)
        
        # Copy the style
        copied_style = original_style.copy()
        
        # Verify the borders were copied correctly
        self.assertEqual(copied_style.borders.top.line_style, original_style.borders.top.line_style)
        self.assertEqual(copied_style.borders.top.color, original_style.borders.top.color)
        self.assertEqual(copied_style.borders.top.weight, original_style.borders.top.weight)
        self.assertEqual(copied_style.borders.bottom.line_style, original_style.borders.bottom.line_style)
        self.assertEqual(copied_style.borders.bottom.color, original_style.borders.bottom.color)
        self.assertEqual(copied_style.borders.bottom.weight, original_style.borders.bottom.weight)
        self.assertEqual(copied_style.borders.left.line_style, original_style.borders.left.line_style)
        self.assertEqual(copied_style.borders.left.color, original_style.borders.left.color)
        self.assertEqual(copied_style.borders.left.weight, original_style.borders.left.weight)
        self.assertEqual(copied_style.borders.right.line_style, original_style.borders.right.line_style)
        self.assertEqual(copied_style.borders.right.color, original_style.borders.right.color)
        self.assertEqual(copied_style.borders.right.weight, original_style.borders.right.weight)