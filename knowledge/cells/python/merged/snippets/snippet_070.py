def test_comprehensive_conditional_formatting(self):
        """Test comprehensive conditional formatting with all rule types."""
        print("Testing comprehensive conditional formatting...")
        
        # 1. Cell value rule - greater than
        cf1 = self.worksheet.conditional_formats.add()
        cf1.type = 'cellValue'
        cf1.operator = 'greaterThan'
        cf1.formula1 = '100'
        cf1.range = 'A1:A10'
        cf1.font.bold = True
        cf1.font.color = 'FFFF0000'
        print("  Cell value (greater than) rule created")
        
        # 2. Cell value rule - less than
        cf2 = self.worksheet.conditional_formats.add()
        cf2.type = 'cellValue'
        cf2.operator = 'lessThan'
        cf2.formula1 = '50'
        cf2.range = 'B1:B10'
        cf2.fill.set_solid_fill('FFFFFF00')
        print("  Cell value (less than) rule created")
        
        # 3. Cell value rule - between
        cf3 = self.worksheet.conditional_formats.add()
        cf3.type = 'cellValue'
        cf3.operator = 'between'
        cf3.formula1 = '50'
        cf3.formula2 = '150'
        cf3.range = 'C1:C10'
        cf3.font.italic = True
        cf3.font.color = 'FF0000FF'
        print("  Cell value (between) rule created")
        
        # 4. Text rule - contains
        cf4 = self.worksheet.conditional_formats.add()
        cf4.type = 'text'
        cf4.text_operator = 'contains'
        cf4.text_formula = 'error'
        cf4.range = 'D1:D10'
        cf4.font.color = 'FFFF0000'
        cf4.fill.set_solid_fill('FFFF00')
        print("  Text (contains) rule created")
        
        # 5. Text rule - notContains
        cf5 = self.worksheet.conditional_formats.add()
        cf5.type = 'text'
        cf5.text_operator = 'notContains'
        cf5.text_formula = 'warning'
        cf5.range = 'E1:E10'
        cf5.font.color = 'FF00FF00'
        cf5.fill.set_solid_fill('FFFFFF00')
        print("  Text (notContains) rule created")
        
        # 6. Text rule - beginsWith
        cf6 = self.worksheet.conditional_formats.add()
        cf6.type = 'text'
        cf6.text_operator = 'beginsWith'
        cf6.text_formula = 'prefix'
        cf6.range = 'F1:F10'
        cf6.font.bold = True
        print("  Text (beginsWith) rule created")
        
        # 7. Text rule - endsWith
        cf7 = self.worksheet.conditional_formats.add()
        cf7.type = 'text'
        cf7.text_operator = 'endsWith'
        cf7.text_formula = 'suffix'
        cf7.range = 'G1:G10'
        cf7.font.italic = True
        print("  Text (endsWith) rule created")
        
        # 8. Duplicate values rule
        cf8 = self.worksheet.conditional_formats.add()
        cf8.type = 'duplicateValues'
        cf8.duplicate = True
        cf8.range = 'H1:H10'
        cf8.fill.set_solid_fill('FFFF0000')
        print("  Duplicate values rule created")
        
        # 9. Unique values rule
        cf9 = self.worksheet.conditional_formats.add()
        cf9.type = 'uniqueValues'
        cf9.duplicate = False
        cf9.range = 'I1:I10'
        cf9.fill.set_solid_fill('00FF00')
        print("  Unique values rule created")
        
        # 10. Top 10 items rule
        cf10 = self.worksheet.conditional_formats.add()
        cf10.type = 'top10'
        cf10.top = True
        cf10.rank = 10
        cf10.range = 'J1:J10'
        cf10.fill.set_solid_fill('FF00FF00')
        print("  Top 10 items rule created")
        
        # 11. Above average rule
        cf11 = self.worksheet.conditional_formats.add()
        cf11.type = 'aboveAverage'
        cf11.above = True
        cf11.range = 'K1:K10'
        cf11.fill.set_solid_fill('FF0000FF')
        print("  Above average rule created")
        
        # 12. Below average rule
        cf12 = self.worksheet.conditional_formats.add()
        cf12.type = 'belowAverage'
        cf12.above = False
        cf12.range = 'L1:L10'
        cf12.fill.set_solid_fill('FFFF00FF')
        print("  Below average rule created")
       
        # 13. 2-color scale
        cf13 = self.worksheet.conditional_formats.add()
        cf13.type = 'colorScale'
        cf13.color_scale_type = '2-color'
        cf13.min_color = 'FF63C384'
        cf13.max_color = 'FF006100'
        cf13.range = 'M1:M10'
        print("  2-color scale rule created")
        
        # 14. 3-color scale
        cf14 = self.worksheet.conditional_formats.add()
        cf14.type = 'colorScale'
        cf14.color_scale_type = '3-color'
        cf14.min_color = 'FF63C384'
        cf14.mid_color = 'FFFFEB84'
        cf14.max_color = 'FF006100'
        cf14.range = 'N1:N10'
        print("  3-color scale rule created")
        '''
        # 15. Data bar
        cf15 = self.worksheet.conditional_formats.add()
        cf15.type = 'dataBar'
        cf15.bar_color = 'FF006100'
        cf15.negative_color = 'FFFF