def test_create_comments(self):
        """Test creating comments with all comment settings and description."""
        # Test data for comprehensive comment testing
        comment_test_cases = [
            {
                'cell': 'A1',
                'value': 'Cell with comment',
                'comment_text': 'This is a simple comment',
                'comment_author': 'Author1',
                'description': 'Simple comment with author'
            },
            {
                'cell': 'A2',
                'value': 'Multi-line comment',
                'comment_text': 'Line 1\nLine 2\nLine 3',
                'comment_author': 'Author2',
                'description': 'Multi-line comment'
            },
            {
                'cell': 'A3',
                'value': 'Empty author',
                'comment_text': 'Comment with empty author',
                'comment_author': 'None',  # Empty author is now converted to "None"
                'description': 'Comment with empty author'
            },
            {
                'cell': 'A4',
                'value': 'Special characters',
                'comment_text': 'Special chars: !@#$%^&*()_+-=[]{}|;:,.<>?',
                'comment_author': 'Author3',
                'description': 'Comment with special characters'
            },
            {
                'cell': 'A5',
                'value': 'Unicode comment',
                'comment_text': 'Unicode: 你好世界 🌍',
                'comment_author': '作者4',
                'description': 'Comment with Unicode characters'
            },
            {
                'cell': 'A6',
                'value': 'Long comment',
                'comment_text': 'This is a very long comment that spans multiple lines and contains a lot of text to test how the comment system handles longer text content. It should still be properly saved and loaded.',
                'comment_author': 'Author5',
                'description': 'Long comment text'
            },
            {
                'cell': 'A7',
                'value': 'Numeric value',
                'comment_text': 'This cell has a numeric value',
                'comment_author': 'Author6',
                'description': 'Comment on numeric cell'
            },
            {
                'cell': 'A8',
                'value': 123.45,
                'comment_text': 'Comment on float value',
                'comment_author': 'Author7',
                'description': 'Comment on float cell'
            },
            {
                'cell': 'A9',
                'value': '',
                'comment_text': 'Comment on empty cell',
                'comment_author': 'Author8',
                'description': 'Comment on empty cell'
            },
            {
                'cell': 'A10',
                'value': None,
                'formula': '=SUM(A1:A9)',
                'comment_text': 'This cell contains a formula',
                'comment_author': 'Author9',
                'description': 'Comment on formula cell'
            }
        ]
        
        # Apply all comments to cells
        print("Creating comments for all test cells...")
        for test_case in comment_test_cases:
            cell_ref = test_case['cell']
            cell_value = test_case['value']
            comment_text = test_case['comment_text']
            comment_author = test_case['comment_author']
            description = test_case['description']
            
            print(f"  {cell_ref}: {description}")
            
            # Create cell with value
            if 'formula' in test_case:
                # Formula cell
                cell = Cell(test_case['value'], test_case['formula'])
            else:
                cell = Cell(cell_value)
            
            # Set comment
            cell.set_comment(comment_text, comment_author)
            
            # Set the cell in the worksheet
            self.worksheet.cells[cell_ref] = cell
        
        # Save workbook to outputfiles folder
        output_path = examples_output_path('example_test_comments.xlsx')
        
        print(f"Saving workbook to {output_path}...")
        self.workbook.save(output_path)
        
        # Verify file was created
        self.assertTrue(os.path.exists(output_path))
        
        # Verify file is not empty
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"Comments test file saved to: {output_path}")
        print(f"File size: {file_size} bytes")
        
        return comment_test_cases