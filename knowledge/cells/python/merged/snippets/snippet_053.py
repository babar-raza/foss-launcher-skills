def test_modify_comments(self):
        """Test modifying all comments and saving to another Excel file."""
        # First create the original comments
        comment_test_cases = self.test_create_comments()
        
        # Load the file
        loaded_workbook = Workbook(examples_output_path('example_test_comments.xlsx'))
        loaded_worksheet = loaded_workbook.worksheets[0]
        
        # Modify all comments
        print("Modifying all comments...")
        modified_test_cases = []
        for i, test_case in enumerate(comment_test_cases):
            cell_ref = test_case['cell']
            
            # Get the cell
            cell = loaded_worksheet.cells[cell_ref]
            
            # Create new comment text and author
            new_comment_text = f"MODIFIED: {test_case['comment_text']}"
            new_comment_author = f"ModifiedAuthor{i+1}"
            
            # Set the modified comment
            cell.set_comment(new_comment_text, new_comment_author)
            
            # Store the modified test case
            modified_test_cases.append({
                'cell': cell_ref,
                'value': test_case['value'],
                'comment_text': new_comment_text,
                'comment_author': new_comment_author,
                'description': f"Modified: {test_case['description']}"
            })
            
            print(f"  {cell_ref}: Modified comment")
        
        # Save to a new file
        output_path = examples_output_path('example_test_comments_modified.xlsx')
        
        print(f"Saving modified workbook to {output_path}...")
        loaded_workbook.save(output_path)
        
        # Verify file was created
        self.assertTrue(os.path.exists(output_path))
        
        # Verify file is not empty
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 0)
        
        print(f"Modified comments test file saved to: {output_path}")
        print(f"File size: {file_size} bytes")
        
        return modified_test_cases