def test_comprehensive_border_test(self):
        """Test all border settings comprehensively."""
        # Test data for comprehensive border testing
        test_cases = [
            {
                'text': 'No Borders',
                'borders': {'all': {'line_style': 'none', 'color': 'FF000000', 'weight': 1}}
            },
            {
                'text': 'Thin Black All',
                'borders': {'all': {'line_style': 'thin', 'color': 'FF000000', 'weight': 1}}
            },
            {
                'text': 'Medium Blue All',
                'borders': {'all': {'line_style': 'medium', 'color': 'FF0000FF', 'weight': 2}}
            },
            {
                'text': 'Thick Red All',
                'borders': {'all': {'line_style': 'thick', 'color': 'FFFF0000', 'weight': 3}}
            },
            {
                'text': 'Dashed Green All',
                'borders': {'all': {'line_style': 'dashed', 'color': 'FF00FF00', 'weight': 1}}
            },
            {
                'text': 'Dotted Purple All',
                'borders': {'all': {'line_style': 'dotted', 'color': 'FF800080', 'weight': 1}}
            },
            {
                'text': 'Double Orange All',
                'borders': {'all': {'line_style': 'double', 'color': 'FFFFA500', 'weight': 2}}
            },
            {
                'text': 'Mixed: Thick Red Top, Thin Blue Bottom',
                'borders': {
                    'top': {'line_style': 'thick', 'color': 'FFFF0000', 'weight': 3},
                    'bottom': {'line_style': 'thin', 'color': 'FF0000FF', 'weight': 1},
                    'left': {'line_style': 'none', 'color': 'FF000000', 'weight': 1},
                    'right': {'line_style': 'none', 'color': 'FF000000', 'weight': 1}
                }
            },
            {
                'text': 'All Sides Different',
                'borders': {
                    'top': {'line_style': 'thick', 'color': 'FFFF0000', 'weight': 3},
                    'bottom': {'line_style': 'medium', 'color': 'FF0000FF', 'weight': 2},
                    'left': {'line_style': 'thin', 'color': 'FF00FF00', 'weight': 1},
                    'right': {'line_style': 'dashed', 'color': 'FF800080', 'weight': 2}
                }
            },
            {
                'text': 'Heavy Weight All',
                'borders': {'all': {'line_style': 'thick', 'color': 'FF000000', 'weight': 5}}
            }
        ]
        
        # Apply all test cases to cells
        for i, test_case in enumerate(test_cases):
            cell = Cell(test_case['text'])
            
            # Apply border settings
            for side, border_props in test_case['borders'].items():
                cell.style.set_border(
                    side,
                    line_style=border_props['line_style'],
                    color=border_props['color'],
                    weight=border_props['weight']
                )
            
            self.worksheet.cells[f"A{i+1}"] = cell