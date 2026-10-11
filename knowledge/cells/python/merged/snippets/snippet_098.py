def test_create_multiple_sparkline_groups():
    """
    Create a new Excel file with multiple sparkline groups of different types.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("createsparkline")
    
    output_path = examples_output_path("createsparkline", "example_test_create_multiple_sparkline_groups.xlsx")
    
    # Create a new workbook
    print("\nCreating new workbook for multiple sparkline groups...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Set worksheet name
    ws.name = "MultipleSparklines"
    
    # Add dummy data for multiple sparkline groups
    print("\nAdding dummy data...")
    # Add headers
    ws.cells["A1"].value = "Region"
    ws.cells["B1"].value = "Jan"
    ws.cells["C1"].value = "Feb"
    ws.cells["D1"].value = "Mar"
    ws.cells["E1"].value = "Apr"
    ws.cells["F1"].value = "May"
    ws.cells["G1"].value = "Jun"
    ws.cells["H1"].value = "Line"
    ws.cells["I1"].value = "Column"
    ws.cells["J1"].value = "WinLoss"
    
    # Add data rows
    dummy_data = [
        ["North", 100, 120, 115, 130, 125, 140],
        ["South", 80, 90, 85, 95, 100, 110],
        ["East", 110, 105, 120, 115, 130, 125],
        ["West", 70, 85, 90, 80, 95, 100],
    ]
    
    for row_idx, row_data in enumerate(dummy_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    print(f"Added {len(dummy_data)} rows of data")
    
    # Add multiple sparkline groups
    print("\nAdding multiple sparkline groups...")
    
    # Group 1: Line sparklines
    line_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.LINE,
        data_range=f"{ws.name}!B2:G5",
        is_vertical=False,
        location_range="H2:H5"
    )
    line_group.color_series = "0070C0"
    line_group.show_high_point = True
    line_group.show_low_point = True
    print(f"Added line sparkline group with {line_group.count} sparklines")
    
    # Group 2: Column sparklines
    column_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.COLUMN,
        data_range=f"{ws.name}!B2:G5",
        is_vertical=False,
        location_range="I2:I5"
    )
    column_group.color_series = "FFC000"
    column_group.show_high_point = True
    print(f"Added column sparkline group with {column_group.count} sparklines")
    
    # Group 3: Win-loss sparklines (using deviations from average)
    winloss_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.WIN_LOSS,
        data_range=f"{ws.name}!B2:G5",
        is_vertical=False,
        location_range="J2:J5"
    )
    winloss_group.color_series = "00B050"
    winloss_group.color_negative = "FF0000"
    print(f"Added win-loss sparkline group with {winloss_group.count} sparklines")
    
    # Save the workbook
    print(f"\nSaving workbook to: {output_path}")
    wb.save(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path), f"Output file not created: {output_path}"
    
    # Verify the XML structure
    with zipfile.ZipFile(output_path) as zf:
        worksheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        
        # Verify multiple sparkline groups exist
        sparkline_groups_count = worksheet_xml.count("<x14:sparklineGroup")
        assert sparkline_groups_count >= 3, f"Expected at least 3 sparkline groups, found {sparkline_groups_count}"
        
        # Verify different types
        assert 'type="column"' in worksheet_xml, "Missing column type"
        assert 'type="win-loss"' in worksheet_xml, "Missing win-loss type"
        
        # Verify different colors
        assert "0070C0" in worksheet_xml, "Missing blue color"
        assert "FFC000" in worksheet_xml, "Missing orange color"
        assert "00B050" in worksheet_xml, "Missing green color"
        assert "FF0000" in worksheet_xml, "Missing red color"
    
    print(f"[OK] Successfully saved workbook with {ws.sparkline_groups.count} sparkline groups")
    
    # Reload and verify
    print("\nReloading to verify...")
    wb_verify = Workbook(output_path)
    ws_verify = wb_verify.worksheets[0]
    print(f"[OK] Verified: {ws_verify.sparkline_groups.count} sparkline group(s) in saved file")
    for group_idx, group in enumerate(ws_verify.sparkline_groups):
        print(f"  Group {group_idx}: type={group.type}, count={group.count}")
    
    return output_path