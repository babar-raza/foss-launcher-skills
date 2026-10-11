def test_default_comment_size(self):
        """Test that comments without explicit size use Excel defaults."""
        wb = Workbook()
        ws = wb.worksheets[0]

        ws.cells['A1'].value = "Default comment"
        ws.cells['A1'].set_comment("No size specified", "Author")

        # Save and check VML
        output_file = examples_output_path('example_test_default_comment_size.xlsx')
        os.makedirs('outputfiles', exist_ok=True)
        wb.save(output_file)

        with zipfile.ZipFile(output_file, 'r') as zf:
            vml_content = zf.read('xl/drawings/vmlDrawing1.vml').decode('utf-8')

            # Should contain default Excel sizes
            self.assertIn('width:96pt', vml_content)
            self.assertIn('height:55.5pt', vml_content)

        print("Test: Default comment size - PASSED")