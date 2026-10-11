def test_border_style_settings(self):
        """Test border line style settings."""
        # Test different border styles
        styles = ['thin', 'medium', 'thick', 'dashed', 'dotted', 'double']
        
        for i, style in enumerate(styles):
            cell = Cell(f"{style.capitalize()} Border")
            cell.style.set_border_style('all', style)
            self.worksheet.cells[f"A{i+1}"] = cell