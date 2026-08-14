def test_create_sparkline_with_empty_cells():
    """
    Create a new Excel file with sparklines that handle empty cells.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("createsparkline")
    
    output_path = examples_output_path("createsparkline", "example_test_create_sparkline_with_empty_cells.xlsx")
    
    # Create a new workbook
    print("\nCreating new workbook for sparklines with empty cells...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Set worksheet name
    ws.name = "EmptyCellsSparklines"
    
    # Add dummy data with some empty cells
    print("\nAdding dummy data with empty cells...")
    # Add headers
    ws.cells["A1"].value = "Item"
    ws.cells["B1"].value = "Jan"
    ws.cells["C1"].value = "Feb"
    ws.cells["D1"].value = "Mar"
    ws.cells["E1"].value = "Apr"
    ws.cells["F1"].value = "May"
    ws.cells["G1"].value = "Trend"
    
    # Add data rows with some empty cells
    dummy_data = [
        ["Item 1", 100, 120, None, 140, 150],
        ["Item 2", 80, None, 100, 110, 120],
        ["Item 3", 90, 95, 105, None, 115],
        ["Item 4", 70, 75, 80, 85, None],
    ]
    
    for row_idx, row_data in enumerate(dummy_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    print(f"Added {len(dummy_data)} rows of data with empty cells")
    
    # Add sparklines with different empty cell handling
    print("\nAdding sparklines with empty cell handling...")
    
    # Group 1: Treat empty cells as gaps
    gap_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.LINE,
        data_range=f"{ws.name}!B2:F2",
        is_vertical=False,
        location_range="G2"
    )
    gap_group.display_empty_cells_as = SparklineEmptyCells.GAP
    gap_group.color_series = "0070C0"
    print(f"Added sparkline with GAP handling")
    
    # Group 2: Treat empty cells as zero
    zero_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.LINE,
        data_range=f"{ws.name}!B3:F3",
        is_vertical=False,
        location_range="G3"
    )
    zero_group.display_empty_cells_as = SparklineEmptyCells.ZERO
    zero_group.color_series = "FFC000"
    print(f"Added sparkline with ZERO handling")
    
    # Group 3: Connect across empty cells
    connected_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.LINE,
        data_range=f"{ws.name}!B4:F4",
        is_vertical=False,
        location_range="G4"
    )
    connected_group.display_empty_cells_as = SparklineEmptyCells.CONNECTED
    connected_group.color_series = "00B050"
    print(f"Added sparkline with CONNECTED handling")
    
    # Group 4: Default (gap) handling
    default_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.LINE,
        data_range=f"{ws.name}!B5:F5",
        is_vertical=False,
        location_range="G5"
    )
    default_group.color_series = "FF0000"
    print(f"Added sparkline with default (GAP) handling")
    
    # Save the workbook
    print(f"\nSaving workbook to: {output_path}")
    wb.save(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path), f"Output file not created: {output_path}"
    
    # Verify the XML structure
    with zipfile.ZipFile(output_path) as zf:
        worksheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        
        # Verify empty cell handling attributes
        assert 'displayEmptyCellsAs="gap"' in worksheet_xml, "Missing gap handling"
        assert 'displayEmptyCellsAs="zero"' in worksheet_xml, "Missing zero handling"
        assert 'displayEmptyCellsAs="connected"' in worksheet_xml, "Missing connected handling"
        
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
        print(f"  Group {group_idx}: type={group.type}, empty_cells={group.display_empty_cells_as}")
    
    return output_path