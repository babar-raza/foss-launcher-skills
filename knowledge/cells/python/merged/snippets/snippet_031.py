def test_border_default_values(self):
        """Test border default values."""
        from aspose.cells_foss.style import Border, Borders
        
        # Test default border values
        border = Border()
        self.assertEqual(border.line_style, 'none')
        self.assertEqual(border.color, 'FF000000')
        self.assertEqual(border.weight, 1)
        
        # Test default borders values
        borders = Borders()
        self.assertEqual(borders.top.line_style, 'none')
        self.assertEqual(borders.top.color, 'FF000000')
        self.assertEqual(borders.top.weight, 1)
        self.assertEqual(borders.bottom.line_style, 'none')
        self.assertEqual(borders.bottom.color, 'FF000000')
        self.assertEqual(borders.bottom.weight, 1)
        self.assertEqual(borders.left.line_style, 'none')
        self.assertEqual(borders.left.color, 'FF000000')
        self.assertEqual(borders.left.weight, 1)
        self.assertEqual(borders.right.line_style, 'none')
        self.assertEqual(borders.right.color, 'FF000000')
        self.assertEqual(borders.right.weight, 1)