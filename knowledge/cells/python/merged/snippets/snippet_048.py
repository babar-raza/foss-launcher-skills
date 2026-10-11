def test_comment_size_persistence(self):
        """Test that comment sizes are persisted in XLSX file."""
        output_file = examples_output_path('example_test_comment_size.xlsx')
        os.makedirs('outputfiles', exist_ok=True)

        # Create workbook with sized comments
        wb = Workbook()
        ws = wb.worksheets[0]

        ws.cells['A1'].value = "Small comment"
        ws.cells['A1'].set_comment("Small", "Author1", width=100, height=60)

        ws.cells['B2'].value = "Medium comment"
        ws.cells['B2'].set_comment("Medium", "Author2", width=150, height=100)

        ws.cells['C3'].value = "Large comment"
        ws.cells['C3'].set_comment("Large", "Author3", width=250, height=180)

        ws.cells['D4'].value = "Default size comment"
        ws.cells['D4'].set_comment("Default", "Author4")

        # Save workbook
        wb.save(output_file)
        print(f"Saved test file: {output_file}")

        # Verify VML drawing contains correct sizes
        with zipfile.ZipFile(output_file, 'r') as zf:
            vml_content = zf.read('xl/drawings/vmlDrawing1.vml').decode('utf-8')

            # Check for width and height in VML
            self.assertIn('width:100pt', vml_content)
            self.assertIn('height:60pt', vml_content)
            self.assertIn('width:150pt', vml_content)
            self.assertIn('height:100pt', vml_content)
            self.assertIn('width:250pt', vml_content)
            self.assertIn('height:180pt', vml_content)
            self.assertIn('width:96pt', vml_content)  # Default width
            self.assertIn('height:55.5pt', vml_content)  # Default height

        print("Test: VML contains correct sizes - PASSED")

        # Load workbook and verify sizes are preserved
        wb2 = Workbook(output_file)
        ws2 = wb2.worksheets[0]

        # Verify A1 (small) - use assertAlmostEqual due to Anchor-based calculation
        size_a1 = ws2.cells['A1'].get_comment_size()
        self.assertIsNotNone(size_a1)
        self.assertAlmostEqual(size_a1[0], 100, delta=5)  # Within 5pt is acceptable
        self.assertAlmostEqual(size_a1[1], 60, delta=5)

        # Verify B2 (medium)
        size_b2 = ws2.cells['B2'].get_comment_size()
        self.assertIsNotNone(size_b2)
        self.assertAlmostEqual(size_b2[0], 150, delta=5)
        self.assertAlmostEqual(size_b2[1], 100, delta=5)

        # Verify C3 (large)
        size_c3 = ws2.cells['C3'].get_comment_size()
        self.assertIsNotNone(size_c3)
        self.assertAlmostEqual(size_c3[0], 250, delta=5)
        self.assertAlmostEqual(size_c3[1], 180, delta=5)

        # Verify D4 (default) - size should be loaded from VML
        size_d4 = ws2.cells['D4'].get_comment_size()
        self.assertIsNotNone(size_d4)
        self.assertAlmostEqual(size_d4[0], 96, delta=5)
        self.assertAlmostEqual(size_d4[1], 55.5, delta=5)

        print("Test: Comment size persistence roundtrip - PASSED")