def test_unlocked_cell_with_sheet_protection(self):
        """Test complete scenario: unlocked cells should be editable when sheet is protected."""
        print("\n" + "="*70)
        print("Test: Unlocked Cells with Sheet Protection")
        print("="*70)

        # Create workbook
        wb = Workbook()
        ws = wb.worksheets[0]
        ws.name = "EditableWhenProtected"

        # Set up a simple data entry form
        print("\nCreating data entry form...")
        ws.cells['A1'].value = "Name:"
        ws.cells['B1'].value = ""  # Editable field
        ws.cells['B1'].style.set_locked(False)

        ws.cells['A2'].value = "Age:"
        ws.cells['B2'].value = ""  # Editable field
        ws.cells['B2'].style.set_locked(False)

        ws.cells['A3'].value = "Total:"
        ws.cells['B3'].formula = "=B2*2"  # Locked, calculated field

        print("  A1, A2, A3: Labels (locked)")
        print("  B1, B2: Input fields (unlocked)")
        print("  B3: Calculated field (locked)")

        # Protect the worksheet
        ws.protect(password="form123")
        print("\nWorksheet protected")

        # Save and reload
        output_file = examples_output_path("example_test_unlocked_cells_protected.xlsx")
        print(f"\nSaving to {output_file}...")
        wb.save(output_file)

        print("Loading back...")
        wb_loaded = Workbook(output_file)
        ws_loaded = wb_loaded.worksheets[0]

        # Verify protection states
        print("\nVerifying protection states...")
        self.assertTrue(ws_loaded.is_protected(), "Worksheet should be protected")
        self.assertTrue(ws_loaded.cells['A1'].style.protection.locked, "A1 (label) should be locked")
        self.assertFalse(ws_loaded.cells['B1'].style.protection.locked, "B1 (input) should be unlocked")
        self.assertFalse(ws_loaded.cells['B2'].style.protection.locked, "B2 (input) should be unlocked")
        self.assertTrue(ws_loaded.cells['B3'].style.protection.locked, "B3 (formula) should be locked")

        print("  [OK] A1: locked")
        print("  [OK] B1: unlocked")
        print("  [OK] B2: unlocked")
        print("  [OK] B3: locked")

        print("\n[OK] Unlocked cells correctly identified!")
        print("="*70 + "\n")