def test_text_rotation(self):
        """Test text rotation setting (0-180 degrees)."""
        rotations = [0, 45, 90, 135, 180, 255]
        
        for i, rotation in enumerate(rotations):
            cell = Cell(f"Rotation: {rotation}")
            cell.style.set_text_rotation(rotation)
            self.worksheet.cells[f"F{i+1}"] = cell
            
            # Verify rotation was set correctly
            self.assertEqual(self.worksheet.cells[f"F{i+1}"].style.alignment.text_rotation, rotation)