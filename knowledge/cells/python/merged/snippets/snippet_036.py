def test_cell_locked_false_roundtrip(self):
        """Test that cells with locked=False can be edited when worksheet is protected."""
        print("\n" + "="*70)
        print("Test: Cell Locked=False Roundtrip")
        print("="*70)

        # Create workbook
        wb = Workbook()
        ws = wb.worksheets[0]
        ws.name = "LockedTest"

        # Set up cells
        print("\nSetting up cells...")
        ws.cells['A1'].value = "Locked (default)"
        ws.cells['A2'].value = "Unlocked"
        ws.cells['A3'].value = "Also unlocked"
        ws.cells['B1'].value = "Hidden formula"
        ws.cells['B1'].formula = "=1+1"

        # Set locked=False for A2 and A3
        print("  A1: Locked (default=True)")
        ws.cells['A2'].style.set_locked(False)
        print("  A2: Locked=False")
        ws.cells['A3'].style.protection.locked = False
        print("  A3: Locked=False (via protection property)")

        # Set formula hidden for B1
        ws.cells['B1'].style.set_formula_hidden(True)
        print("  B1: Formula hidden=True")

        # Protect the worksheet
        ws.protect(password="test123")
        print("\nWorksheet protected with password")

        # Save
        output_file = examples_output_path("example_test_cell_locked_false.xlsx")
        print(f"\nSaving to {output_file}...")
        wb.save(output_file)
        self.assertTrue(os.path.exists(output_file))

        # Verify XML structure
        print("\nVerifying XML structure...")
        with zipfile.ZipFile(output_file, 'r') as zf:
            # Check styles.xml for protection element
            styles_xml = zf.read('xl/styles.xml').decode('utf-8')
            print(f"Styles XML length: {len(styles_xml)} bytes")

            # Parse and verify protection in cellXfs
            styles_root = ET.fromstring(styles_xml)
            cell_xfs = styles_root.findall('.//main:cellXfs/main:xf', self.ns)
            print(f"Found {len(cell_xfs)} cellXf elements")

            # Find xf with protection element
            found_protection = False
            for xf in cell_xfs:
                prot = xf.find('main:protection', self.ns)
                if prot is not None:
                    locked = prot.get('locked', '1')
                    hidden = prot.get('hidden', '0')
                    print(f"  Found protection: locked={locked}, hidden={hidden}")
                    found_protection = True

            self.assertTrue(found_protection, "Should find at least one protection element in styles")

            # Check worksheet XML for cells with style references
            sheet_xml = zf.read('xl/worksheets/sheet1.xml').decode('utf-8')
            sheet_root = ET.fromstring(sheet_xml)

            # Check that A2 has a style index (s attribute)
            rows = sheet_root.findall('.//main:sheetData/main:row', self.ns)
            a2_style = None
            for row in rows:
                for cell in row.findall('main:c', self.ns):
                    ref = cell.get('r')
                    if ref == 'A2':
                        a2_style = cell.get('s')
                        print(f"  A2 has style index: {a2_style}")

            self.assertIsNotNone(a2_style, "A2 should have a style reference")

        # Load back and verify
        print("\nLoading workbook back...")
        wb_loaded = Workbook(output_file)
        ws_loaded = wb_loaded.worksheets[0]

        # Verify values
        print("Verifying cell values...")
        self.assertEqual(ws_loaded.cells['A1'].value, "Locked (default)")
        self.assertEqual(ws_loaded.cells['A2'].value, "Unlocked")
        self.assertEqual(ws_loaded.cells['A3'].value, "Also unlocked")
        self.assertEqual(ws_loaded.cells['B1'].formula, "=1+1")

        # Verify protection settings
        print("Verifying protection settings...")
        self.assertTrue(ws_loaded.cells['A1'].style.protection.locked, "A1 should be locked")
        self.assertFalse(ws_loaded.cells['A2'].style.protection.locked, "A2 should be unlocked")
        self.assertFalse(ws_loaded.cells['A3'].style.protection.locked, "A3 should be unlocked")
        self.assertTrue(ws_loaded.cells['B1'].style.protection.hidden, "B1 formula should be hidden")

        print("\n[OK] Cell protection roundtrip successful!")
        print("="*70 + "\n")