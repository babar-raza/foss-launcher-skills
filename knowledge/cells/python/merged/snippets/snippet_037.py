def test_protection_in_styles_xml(self):
        """Test that protection element is correctly written to styles.xml."""
        print("\n" + "="*70)
        print("Test: Protection Element in styles.xml")
        print("="*70)

        # Create workbook with various protection settings
        wb = Workbook()
        ws = wb.worksheets[0]

        # Create cells with different protection settings
        ws.cells['A1'].value = "Locked"  # Default: locked=True, hidden=False
        ws.cells['A2'].value = "Unlocked"
        ws.cells['A2'].style.protection.locked = False
        ws.cells['A3'].value = "Hidden formula"
        ws.cells['A3'].formula = "=1+1"
        ws.cells['A3'].style.protection.hidden = True
        ws.cells['A4'].value = "Unlocked and hidden"
        ws.cells['A4'].formula = "=2+2"
        ws.cells['A4'].style.protection.locked = False
        ws.cells['A4'].style.protection.hidden = True

        # Save
        output_file = examples_output_path("example_test_protection_styles.xlsx")
        print(f"\nSaving to {output_file}...")
        wb.save(output_file)

        # Verify styles.xml
        print("\nVerifying styles.xml structure...")
        with zipfile.ZipFile(output_file, 'r') as zf:
            styles_xml = zf.read('xl/styles.xml').decode('utf-8')
            styles_root = ET.fromstring(styles_xml)

            cell_xfs = styles_root.findall('.//main:cellXfs/main:xf', self.ns)
            print(f"Found {len(cell_xfs)} cellXf elements")

            protection_count = 0
            for i, xf in enumerate(cell_xfs):
                prot = xf.find('main:protection', self.ns)
                if prot is not None:
                    locked = prot.get('locked', '1')
                    hidden = prot.get('hidden', '0')
                    print(f"  cellXf[{i}]: locked={locked}, hidden={hidden}")
                    protection_count += 1

            # We should have at least one protection element
            self.assertGreater(protection_count, 0, "Should have protection elements in styles")
            print(f"\n[OK] Found {protection_count} protection elements")

        print("="*70 + "\n")