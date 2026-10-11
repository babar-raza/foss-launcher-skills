def test_border_color_settings(self):
        """Test border color settings for different sides."""
        # Test setting border colors for individual sides
        cell1 = Cell("Red Top Border")
        cell1.style.set_border_color('top', 'FFFF0000')
        self.worksheet.cells["A1"] = cell1
        
        cell2 = Cell("Blue Bottom Border")
        cell2.style.set_border_color('bottom', 'FF0000FF')
        self.worksheet.cells["A2"] = cell2
        
        cell3 = Cell("Green Left Border")
        cell3.style.set_border_color('left', 'FF00FF00')
        self.worksheet.cells["A3"] = cell3
        
        cell4 = Cell("Purple Right Border")
        cell4.style.set_border_color('right', 'FF800080')
        self.worksheet.cells["A4"] = cell4
        
        cell5 = Cell("All Red Borders")
        cell5.style.set_border_color('all', 'FFFF0000')
        self.worksheet.cells["A5"] = cell5