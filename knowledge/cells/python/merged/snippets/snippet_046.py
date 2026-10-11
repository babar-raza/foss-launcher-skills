def test_set_comment_with_size(self):
        """Test setting comment with custom size."""
        wb = Workbook()
        ws = wb.worksheets[0]

        # Set comment with custom size
        ws.cells['A1'].value = "Cell with sized comment"
        ws.cells['A1'].set_comment("This is a large comment", "Author1", width=200, height=150)

        # Verify comment exists
        self.assertTrue(ws.cells['A1'].has_comment())

        # Verify size is stored
        comment = ws.cells['A1'].get_comment()
        self.assertEqual(comment['width'], 200)
        self.assertEqual(comment['height'], 150)

        # Verify get_comment_size method
        size = ws.cells['A1'].get_comment_size()
        self.assertIsNotNone(size)
        self.assertEqual(size[0], 200)
        self.assertEqual(size[1], 150)

        print("Test: Set comment with size - PASSED")