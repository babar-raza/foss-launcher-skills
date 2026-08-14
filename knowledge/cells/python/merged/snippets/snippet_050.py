def test_error_on_size_without_comment(self):
        """Test that setting size without a comment raises an error."""
        wb = Workbook()
        ws = wb.worksheets[0]

        ws.cells['A1'].value = "No comment"

        with self.assertRaises(ValueError) as context:
            ws.cells['A1'].set_comment_size(100, 100)

        self.assertIn("has no comment", str(context.exception))
        print("Test: Error on size without comment - PASSED")