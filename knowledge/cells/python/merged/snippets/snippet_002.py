def test_vertical_alignment(self):
        """Test vertical alignment settings."""
        vertical_alignments = [
            'top',
            'center',
            'bottom',
            'justify',
            'distributed'
        ]
        
        for i, alignment in enumerate(vertical_alignments):
            cell = Cell(f"Vertical: {alignment}")
            cell.style.set_vertical_alignment(alignment)
            self.worksheet.cells[f"B{i+1}"] = cell
            
            # Verify alignment was set correctly
            self.assertEqual(self.worksheet.cells[f"B{i+1}"].style.alignment.vertical, alignment)