def test_create_line_sparklines():
    """
    Create a new Excel file with dummy data and add line sparklines.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("createsparkline")
    
    output_path = examples_output_path("createsparkline", "example_test_create_line_sparklines.xlsx")
    
    # Create a new workbook
    print("Creating new workbook for line sparklines...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Set worksheet name
    ws.name = "LineSparklines"
    
    # Add dummy data for sparklines
    print("\nAdding dummy data...")
    # Add headers
    ws.cells["A1"].value = "Store"
    ws.cells["B1"].value = "January"
    ws.cells["C1"].value = "February"
    ws.cells["D1"].value = "March"
    ws.cells["E1"].value = "April"
    ws.cells["F1"].value = "May"
    ws.cells["G1"].value = "Trend"
    
    # Add data rows
    dummy_data = [
        ["Houston", 4873, 11776, 8355, 9241, 10567],
        ["San Diego", 9575, 7135, 5575, 8234, 7892],
        ["Portland", 12011, 9373, 3386, 6789, 8456],
        ["Seattle", 6543, 8765, 9876, 7654, 8765],
        ["Austin", 7890, 6543, 8765, 5432, 6789],
    ]
    
    for row_idx, row_data in enumerate(dummy_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    print(f"Added {len(dummy_data)} rows of data")
    
    # Add line sparklines
    print("\nAdding line sparklines...")
    
    # Create a sparkline group for line sparklines
    sparkline_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.LINE,
        data_range=f"{ws.name}!B2:F6",
        is_vertical=False,
        location_range="G2:G6"
    )
    
    # Customize sparkline appearance
    sparkline_group.color_series = "0070C0"  # Blue
    sparkline_group.line_weight = 1.0
    sparkline_group.show_high_point = True
    sparkline_group.show_low_point = True
    sparkline_group.color_high = "00B050"  # Green for high point
    sparkline_group.color_low = "FF0000"   # Red for low point
    
    print(f"Added {sparkline_group.count} line sparklines")
    
    # Save the workbook
    print(f"\nSaving workbook to: {output_path}")
    wb.save(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path), f"Output file not created: {output_path}"
    
    # Verify the XML structure
    with zipfile.ZipFile(output_path) as zf:
        names = set(zf.namelist())
        # Check that worksheet file exists
        assert "xl/worksheets/sheet1.xml" in names, "Missing worksheet part"
        
        # Read and verify worksheet XML
        worksheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        
        # Verify sparkline extLst exists
        assert "<extLst>" in worksheet_xml, "Missing extLst in worksheet XML"
        assert "sparklineGroups" in worksheet_xml, "Missing sparklineGroups in worksheet XML"
        
        # Verify sparkline type (line is default, so type attribute may be omitted)
        # Check for sparkline elements
        assert "<x14:sparkline>" in worksheet_xml, "Missing sparkline element"
        assert "<xm:f>" in worksheet_xml, "Missing data range formula"
        assert "<xm:sqref>" in worksheet_xml, "Missing cell reference"
        
        # Verify data ranges
        assert f"{ws.name}!B2:F6" in worksheet_xml or f"{ws.name}!B2:F2" in worksheet_xml, "Missing data range"
        assert "G2" in worksheet_xml, "Missing location cell"
        
        # Verify colors
        assert "0070C0" in worksheet_xml, "Missing series color"
        assert "00B050" in worksheet_xml, "Missing high point color"
        assert "FF0000" in worksheet_xml, "Missing low point color"
    
    print(f"[OK] Successfully saved workbook with {sparkline_group.count} line sparklines")
    
    # Reload and verify
    print("\nReloading to verify...")
    wb_verify = Workbook(output_path)
    ws_verify = wb_verify.worksheets[0]
    print(f"[OK] Verified: {ws_verify.sparkline_groups.count} sparkline group(s) in saved file")
    for group_idx, group in enumerate(ws_verify.sparkline_groups):
        print(f"  Group {group_idx}: type={group.type}, count={group.count}")
        for sp_idx, sp in enumerate(group.sparklines):
            print(f"    Sparkline {sp_idx}: data_range='{sp.data_range}', cell='{sp.cell_reference}'")
    
    return output_path