def test_create_win_loss_sparklines():
    """
    Create a new Excel file with dummy data and add win-loss sparklines.
    """
    # Ensure output directory exists
    ensure_examples_output_dir("createsparkline")
    
    output_path = examples_output_path("createsparkline", "example_test_create_win_loss_sparklines.xlsx")
    
    # Create a new workbook
    print("\nCreating new workbook for win-loss sparklines...")
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Set worksheet name
    ws.name = "WinLossSparklines"
    
    # Add dummy data for win-loss sparklines
    print("\nAdding dummy data...")
    # Add headers
    ws.cells["A1"].value = "Team"
    ws.cells["B1"].value = "Game 1"
    ws.cells["C1"].value = "Game 2"
    ws.cells["D1"].value = "Game 3"
    ws.cells["E1"].value = "Game 4"
    ws.cells["F1"].value = "Game 5"
    ws.cells["G1"].value = "Performance"
    
    # Add data rows (positive = win, negative = loss)
    dummy_data = [
        ["Team A", 1, 1, -1, 1, 1],
        ["Team B", -1, 1, 1, -1, 1],
        ["Team C", 1, 1, 1, 1, -1],
        ["Team D", -1, -1, 1, 1, 1],
        ["Team E", 1, -1, 1, -1, 1],
    ]
    
    for row_idx, row_data in enumerate(dummy_data, start=2):
        for col_idx, value in enumerate(row_data):
            cell_ref = f"{chr(65 + col_idx)}{row_idx}"
            ws.cells[cell_ref].value = value
    
    print(f"Added {len(dummy_data)} rows of data")
    
    # Add win-loss sparklines
    print("\nAdding win-loss sparklines...")
    
    # Create a sparkline group for win-loss sparklines
    sparkline_group = ws.sparkline_groups.add(
        sparkline_type=SparklineType.WIN_LOSS,
        data_range=f"{ws.name}!B2:F6",
        is_vertical=False,
        location_range="G2:G6"
    )
    
    # Customize sparkline appearance
    sparkline_group.color_series = "0070C0"  # Blue
    sparkline_group.color_negative = "FF0000"  # Red for negative values
    
    print(f"Added {sparkline_group.count} win-loss sparklines")
    
    # Save the workbook
    print(f"\nSaving workbook to: {output_path}")
    wb.save(output_path)
    
    # Verify the file was created
    assert os.path.exists(output_path), f"Output file not created: {output_path}"
    
    # Verify the XML structure
    with zipfile.ZipFile(output_path) as zf:
        worksheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        
        # Verify sparkline type is win-loss
        assert 'type="win-loss"' in worksheet_xml, "Missing win-loss type attribute"
        
        # Verify colors
        assert "0070C0" in worksheet_xml, "Missing series color"
        assert "FF0000" in worksheet_xml, "Missing negative color"
    
    print(f"[OK] Successfully saved workbook with {sparkline_group.count} win-loss sparklines")
    
    # Reload and verify
    print("\nReloading to verify...")
    wb_verify = Workbook(output_path)
    ws_verify = wb_verify.worksheets[0]
    print(f"[OK] Verified: {ws_verify.sparkline_groups.count} sparkline group(s) in saved file")
    
    return output_path