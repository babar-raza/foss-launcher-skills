def test_border_weight_settings(self):
        """Test border line weight settings."""
        # Test different border weights
        weights = [1, 2, 3, 4, 5]
        
        for i, weight in enumerate(weights):
            cell = Cell(f"Weight {weight}")
            cell.style.set_border_weight('all', weight)
            self.worksheet.cells[f"A{i+1}"] = cell