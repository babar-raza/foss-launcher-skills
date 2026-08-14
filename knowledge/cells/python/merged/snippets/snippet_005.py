def test_indent_level(self):
        """Test indent level setting."""
        indent_levels = [0, 1, 2, 3, 5, 10]
        
        for i, indent in enumerate(indent_levels):
            cell = Cell(f"Indent: {indent}")
            cell.style.set_indent(indent)
            self.worksheet.cells[f"E{i+1}"] = cell
            
            # Verify indent was set correctly
            self.assertEqual(self.worksheet.cells[f"E{i+1}"].style.alignment.indent, indent)