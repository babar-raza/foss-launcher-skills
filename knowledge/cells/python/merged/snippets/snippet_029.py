def test_complete_border_settings(self):
        """Test complete border settings with all properties."""
        # Test setting all border properties at once
        cell1 = Cell("Thick Black All")
        cell1.style.set_border('all', line_style='thick', color='FF000000', weight=3)
        self.worksheet.cells["A1"] = cell1
        
        cell2 = Cell("Thin Red Top")
        cell2.style.set_border('top', line_style='thin', color='FFFF0000', weight=1)
        self.worksheet.cells["A2"] = cell2
        
        cell3 = Cell("Medium Blue Bottom")
        cell3.style.set_border('bottom', line_style='medium', color='FF0000FF', weight=2)
        self.worksheet.cells["A3"] = cell3
        
        cell4 = Cell("Dashed Green Left")
        cell4.style.set_border('left', line_style='dashed', color='FF00FF00', weight=1)
        self.worksheet.cells["A4"] = cell4
        
        cell5 = Cell("Dotted Purple Right")
        cell5.style.set_border('right', line_style='dotted', color='FF800080', weight=1)
        self.worksheet.cells["A5"] = cell5